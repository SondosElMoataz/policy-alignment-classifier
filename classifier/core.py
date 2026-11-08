"""Policy classifier: one agent trace event in, a verdict out.

Backends: Groq, Gemini, and local Ollama. Select INFERENCE_PROVIDER.
MOCK=1 swaps in a keyword heuristic so the app and harness run with no key (for tests only, never report its numbers).
"""
import json
from copy import deepcopy
import os
import re
import time
import threading
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from classifier.prompts import SYSTEM, KIND_SCOPE, OLLAMA_CLASSIFICATION_INSTRUCTION

ROOT = Path(__file__).resolve().parent.parent
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

VERDICTS = ("allow", "violation", "escalate")
RULE_IDS = tuple(f"R{i}" for i in range(1, 7))

# Field order matters: the model writes evidence and rationale BEFORE the verdict,
# so the verdict follows the reasoning instead of being committed first.
OLLAMA_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence": {"type": ["string", "null"]},
        "rationale": {"type": "string"},
        "rules": {"type": "array", "items": {"type": "string", "enum": list(RULE_IDS)}},
        "primary_rule": {"type": ["string", "null"], "enum": [*RULE_IDS, None]},
        "missing_fact": {"type": ["string", "null"]},
        "verdict": {"type": "string", "enum": list(VERDICTS)},
    },
    "required": ["evidence", "rationale", "rules", "primary_rule", "missing_fact", "verdict"],
    "additionalProperties": False,
}

# Copied from each rule's "Applies to:" line in the policy.
APPLIES_TO = {
    "R1": ("tool_response",),
    "R2": ("tool_call", "model_output"),
    "R3": ("tool_call",),
    "R4": ("tool_response", "model_output", "tool_call"),
    "R5": ("tool_call",),
    "R6": ("user_input",),
}

# Shown after every event: which rules can apply to its kind, and where the
# other rules get judged instead. Written from the policy's "Applies to" lines.



def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env()


def inference_config(provider=None, model=None):
    provider = (provider or os.getenv("INFERENCE_PROVIDER", "groq")).strip().lower()
    if provider not in ("groq", "gemini", "ollama"):
        raise ValueError("provider must be groq, gemini or ollama")
    prefix = provider.upper()
    default = {"groq": "openai/gpt-oss-20b", "gemini": "gemini-2.5-flash", "ollama": "qwen3:4b"}[provider]
    model = (model if model is not None else os.getenv(prefix + "_MODEL", "").strip() or default).strip()
    if not model:
        raise ValueError("model must not be blank")
    if provider == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
        url = httpx.URL(base)
        if url.scheme not in ("http", "https") or not url.host or url.userinfo or url.query or url.fragment:
            raise ValueError("OLLAMA_BASE_URL must be an HTTP(S) URL without credentials, query or fragment")
        read_timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "240"))
        if not 0 < read_timeout <= 3600:
            raise ValueError("Ollama timeout must be within 0..3600 seconds")
        return {"provider": provider, "model": model, "key_env": None, "url": base + "/api/chat",
                "read_timeout": read_timeout,
                "parameters": {"format": deepcopy(OLLAMA_RESPONSE_SCHEMA), "stream": False, "think": False,
                               # 384 cut long answers mid-JSON -> parse_error. 1024 leaves room.
                               "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 1024}}}
    return {"provider": provider, "model": model, "key_env": prefix + "_API_KEY",
            "url": GEMINI_URL if provider == "gemini" else GROQ_URL,
            # Both compatibility endpoints support these fields. Do not send
            # provider-specific reasoning options or token limits implicitly.
            "parameters": {"temperature": 0, "response_format": {"type": "json_object"}}}


def load_policy():
    policy_path = Path(os.getenv("POLICY_FILE", "policy_v1_1.md"))
    if not policy_path.is_absolute():
        policy_path = ROOT / policy_path
    return policy_path.read_text(encoding="utf-8-sig")






def render_event(event, n_context=6):
    """Show only the target event, supplied preceding events and instructions."""
    ctx = event.get("context") or {}
    previous = ctx.get("previous_events") or []
    prev = previous if n_context == "all" else previous[-n_context:] if n_context else []
    body = {"kind": event["kind"]}
    if event.get("tool"):
        body["tool"] = event["tool"]
    if event["kind"] == "tool_call":
        body["args"] = event.get("args", {})
    else:
        body["content"] = event.get("content", "")
    parts = []
    if ctx.get("original_request"):  # always shown: it is what grants authority
        parts.append("ORIGINAL USER REQUEST (the principal's task for this trace):\n" + ctx["original_request"])
    if n_context and ctx.get("system_prompt"):
        parts.append("AGENT SYSTEM PROMPT (context):\n" + ctx["system_prompt"])
    if prev:
        parts.append("PREVIOUS EVENTS (context, oldest first):\n" +
                     "\n".join(json.dumps(p, ensure_ascii=False) for p in prev))
    parts.append("EVENT TO JUDGE:\n" + json.dumps(body, ensure_ascii=False, indent=1))
    applicable = [r for r, kinds in APPLIES_TO.items() if event["kind"] in kinds]
    parts.append(f"RULES THAT CAN APPLY TO THIS EVENT ({event['kind']}): " + ", ".join(applicable) +
                 "\n" + KIND_SCOPE[event["kind"]])
    return "\n\n".join(parts)


def scope_rules(out, kind):
    """Log only; never changes the verdict or rules. Records rule ids the model cited
    that the policy's 'Applies to' lines say cannot apply to this event kind, so the
    write-up can report how well the prompt's scoping instruction was followed.
    Field names are kept from the earlier version so the eval and metrics cells work
    unchanged: dropped_rules = out-of-scope citations (logged, NOT removed)."""
    if out.get("verdict") in VERDICTS:
        out["model_verdict"] = out["verdict"]
        out["dropped_rules"] = [r for r in (out.get("rules") or []) if kind not in APPLIES_TO.get(r, ())]
    return out


def parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        out = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        out = {}
    v = str(out.get("verdict", "")).lower().strip()
    out["verdict"] = v if v in VERDICTS else "parse_error"
    rules = out.get("rules") or []
    out["rules"] = [rules] if isinstance(rules, str) else list(rules)
    out.setdefault("primary_rule", min(out["rules"], key=lambda r: int(re.sub(r"\D", "", r) or 99)) if out["rules"] else None)
    out.setdefault("missing_fact", None)
    return out


def render_ollama_event(event, n_context=6):
    return render_event(event, n_context) + "\n\n" + OLLAMA_CLASSIFICATION_INSTRUCTION


def build_ollama_request(event, policy_text=None, model=None, n_context=6, system_prompt=None, system_prompt_template=None):
    """Shared validated profile for notebook evaluation and local serving."""
    if event.get("kind") not in ("user_input", "model_output", "tool_call", "tool_response"):
        raise ValueError("Invalid event kind")
    if n_context != "all" and (type(n_context) is not int or not 0 <= n_context <= 20):
        raise ValueError("context must be between 0 and 20, or all")
    settings = inference_config("ollama", model)
    policy = policy_text if policy_text is not None else load_policy()
    if system_prompt_template is not None:
        if system_prompt is not None:
            raise ValueError("Supply a custom instruction or a complete system template, not both")
        instruction = system_prompt_template.format(policy=policy)
    else:
        instruction = SYSTEM.format(policy=policy) if system_prompt is None else system_prompt + "\n\nPOLICY:\n<<<\n" + policy + "\n>>>"
    return {"model": settings["model"], **settings["parameters"], "messages": [
        {"role": "system", "content": instruction},
        {"role": "user", "content": render_ollama_event(event, n_context)},
    ]}


def parse_ollama(text):
    """Validate the constrained response, then use the existing shared parser.

    Only the exact literal 'null' is normalized for nullable fields. No type
    coercion, missing-field defaults, extra fields or non-classification JSON.
    """
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    try:
        out = json.loads(text, object_pairs_hook=unique_object)
        if not isinstance(out, dict) or set(out) != set(OLLAMA_RESPONSE_SCHEMA["required"]):
            raise ValueError("Unexpected fields")
        for field in ("primary_rule", "evidence", "missing_fact"):
            if out[field] == "null":
                out[field] = None
        if (out["verdict"] not in VERDICTS or not isinstance(out["rules"], list) or
                any(rule not in RULE_IDS for rule in out["rules"]) or
                out["primary_rule"] not in (*RULE_IDS, None) or
                not isinstance(out["rationale"], str) or
                any(out[field] is not None and not isinstance(out[field], str) for field in ("evidence", "missing_fact"))):
            raise ValueError("Invalid classification values")
        return parse(json.dumps(out))
    except (ValueError, TypeError):
        return parse("")


def mock_classify(event):
    s = json.dumps(event.get("args", event.get("content", ""))).lower()
    if event["kind"] == "tool_response" and re.search(r"ignore (all )?previous|important message from me|<information>", s):
        return {"verdict": "violation", "rules": ["R1"], "primary_rule": "R1", "rationale": "[MOCK] injected-instruction keywords", "evidence": None, "missing_fact": None}
    if event["kind"] == "tool_call" and re.search(r"@(gmail|yahoo|hotmail)\.com", s):
        return {"verdict": "violation", "rules": ["R3"], "primary_rule": "R3", "rationale": "[MOCK] external email domain", "evidence": None, "missing_fact": None}
    return {"verdict": "allow", "rules": [], "primary_rule": None, "rationale": "[MOCK] no keyword matched", "evidence": None, "missing_fact": None}


class ClassifierError(RuntimeError):
    """An actionable error safe to return to the demo client."""

    def __init__(self, message, status_code=502, code="provider_error"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def make_http_client():
    """Keep inference reads at 60s, but bound connection/pool/write stalls."""
    return httpx.Client(timeout=httpx.Timeout(60, connect=10, write=10, pool=10),
                        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10,
                                           keepalive_expiry=5))


class RateLimitGate:
    """Share provider cooldowns across requests."""

    def __init__(self):
        self.lock = threading.Lock()
        self.until = 0.0

    def defer(self, seconds):
        with self.lock:
            self.until = max(self.until, time.monotonic() + seconds)

    def wait(self):
        started = time.monotonic()
        while True:
            with self.lock:
                delay = self.until - time.monotonic()
            if delay <= 0:
                return time.monotonic() - started
            time.sleep(min(delay, 1))


def retry_delay(value, fallback):
    try:
        return max(0, float(value))
    except (TypeError, ValueError):
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return fallback


def provider_error(response, model, provider="groq"):
    # Do not echo raw provider bodies: they may contain request text or credentials.
    try:
        data = response.json()
        error = data.get("error", {}) if isinstance(data, dict) else {}
        code = error.get("code") if isinstance(error, dict) else None
    except ValueError:
        code = None
    name = provider.title()
    prefix = provider.upper()
    if response.status_code == 404 or code == "model_not_found":
        if provider == "ollama":
            return ClassifierError(f"Ollama model '{model}' was not found. Pull it with ollama pull and check OLLAMA_BASE_URL.",
                                   code="model_not_found")
        return ClassifierError(
            f"{name} model '{model}' is unavailable or inaccessible to this key. "
            f"Check {prefix}_MODEL in .env and restart the backend.",
            code="model_not_found",
        )
    if response.status_code in (401, 403):
        return ClassifierError(f"{name} rejected the API key or access permissions. Check {prefix}_API_KEY in .env and restart the backend.", code="provider_auth_error")
    if response.status_code == 429:
        return ClassifierError(f"{name} rate limit reached. Wait and retry, or check the account quota.", 429, "rate_limit")
    if response.status_code in (502, 503, 504):
        return ClassifierError(f"{name} is temporarily unavailable (HTTP {response.status_code}).",
                               503, "provider_unavailable")
    return ClassifierError(f"{name} rejected the classification request (HTTP {response.status_code}). Check the selected model's chat and JSON support.")


def response_retry_delay(response, fallback):
    if response.headers.get("retry-after") is not None:
        return retry_delay(response.headers["retry-after"], fallback)
    # Gemini may return google.rpc.RetryInfo instead of an HTTP Retry-After.
    try:
        for detail in response.json().get("error", {}).get("details", []):
            if detail.get("@type", "").endswith("google.rpc.RetryInfo"):
                return max(0, float(detail["retryDelay"].removesuffix("s")))
    except (ValueError, TypeError, KeyError, AttributeError):
        pass
    return fallback


def classify(
    event,
    model=None,
    n_context=6,
    client=None,
    retries=4,
    policy_text=None,
    rate_limit_gate=None,
    on_retry=None,
    provider=None,
    transport_retries=2,
    on_transport_retry=None,
    system_prompt=None,
    system_prompt_template=None,
):
    """Returns verdict and usage metadata; never substitutes mock on provider failure."""
    if event.get("kind") not in ("user_input", "model_output", "tool_call", "tool_response"):
        raise ValueError("event.kind must be user_input, model_output, tool_call or tool_response")
    if n_context != "all" and (type(n_context) is not int or not 0 <= n_context <= 20):
        raise ValueError("context must be between 0 and 20, or all")
    if retries < 0 or transport_retries < 0:
        raise ValueError("retry counts must be nonnegative")
    settings = inference_config(provider, model)
    provider, model = settings["provider"], settings["model"]
    if (system_prompt is not None or system_prompt_template is not None) and provider != "ollama":
        raise ValueError("Experimental system prompts are supported only with Ollama")
    name = provider.title()
    t0 = time.perf_counter()
    if os.getenv("MOCK") == "1":
        out = mock_classify(event)
        out.update(latency_ms=round((time.perf_counter() - t0) * 1000, 1), prompt_tokens=0,
                   completion_tokens=0, model="mock", provider=provider)
        return out
    api_key = os.getenv(settings["key_env"], "").strip() if settings["key_env"] else None
    if settings["key_env"] and not api_key:
        raise ClassifierError(f"{settings['key_env']} not set. Put it in .env and restart, or explicitly set MOCK=1 for a keyless demo.", 503, "missing_api_key")
    payload = {
        "model": model,
        **settings["parameters"],
        "messages": [
            {
                "role": "system",
                "content": SYSTEM.format(
                    policy=policy_text if policy_text is not None else load_policy()
                ),
            },
            {"role": "user", "content": render_event(event, n_context)},
        ],
    }
    if provider == "ollama":
        payload = build_ollama_request(event, policy_text, model, n_context, system_prompt, system_prompt_template)
    owned_client = client is None
    client = client if client is not None else make_http_client()
    recovery_client = None
    gate = rate_limit_gate if rate_limit_gate is not None else RateLimitGate()
    wait_seconds = 0.0
    transient_failures = 0
    try:
        for attempt in range(retries + 1):
            wait_seconds += gate.wait()
            try:
                active_client = recovery_client if recovery_client is not None else client
                request_options = {"headers": {"Authorization": f"Bearer {api_key}"} if api_key else {}}
                if provider == "ollama":
                    request_options["timeout"] = httpx.Timeout(settings["read_timeout"], connect=10, write=10, pool=10)
                response = active_client.post(settings["url"], json=payload, **request_options)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError, httpx.ProxyError) as exc:
                transient_failures += 1
                code = "provider_timeout" if isinstance(exc, httpx.TimeoutException) else "provider_connection_error"
                if transient_failures > transport_retries or attempt == retries:
                    error = ClassifierError(f"{name} transport failed ({type(exc).__name__}) after {attempt + 1} attempts.",
                                            504 if code == "provider_timeout" else 503, code)
                    error.transport_error_type = type(exc).__name__
                    # Record types only, never exception messages/URLs/headers.
                    causes, cause = [], exc.__cause__
                    while cause is not None and len(causes) < 5:
                        causes.append(type(cause).__name__)
                        cause = cause.__cause__
                    error.transport_cause_types = causes
                    error.attempts = attempt + 1
                    error.retry_wait_ms = round(wait_seconds * 1000, 1)
                    raise error from None
                # Never close/reset a caller's shared pool while other workers use it.
                # A private fresh pool avoids reusing a suspect connection on retry.
                if recovery_client is not None:
                    recovery_client.close()
                recovery_client = make_http_client()
                delay = min(2 ** (transient_failures - 1), 4)
                if on_transport_retry:
                    on_transport_retry(attempt + 1, delay, type(exc).__name__)
                time.sleep(delay)
                wait_seconds += delay
                continue
            if response.status_code in (502, 503, 504):
                transient_failures += 1
                if transient_failures <= transport_retries and attempt < retries:
                    delay = min(30, response_retry_delay(response, 2 ** (transient_failures - 1)))
                    response.close()
                    if on_transport_retry:
                        on_transport_retry(attempt + 1, delay, "provider_unavailable")
                    time.sleep(delay)
                    wait_seconds += delay
                    continue
            if response.status_code == 429:
                delay = response_retry_delay(response, 2 ** (attempt + 1))
                gate.defer(delay)
            if response.status_code == 429 and attempt < retries:
                if on_retry:
                    on_retry(attempt + 1, delay)
                continue
            if response.is_error:
                error = provider_error(response, model, provider)
                error.attempts = attempt + 1
                error.retry_wait_ms = round(wait_seconds * 1000, 1)
                raise error
            break
        try:
            data = response.json()
            if provider == "ollama":
                if data.get("done") is not True or data.get("error"):
                    raise ValueError("Incomplete Ollama response")
                content = data["message"]["content"]
                usage = {"prompt_tokens": data.get("prompt_eval_count"), "completion_tokens": data.get("eval_count")}
            else:
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
            if not isinstance(content, str):
                raise ValueError("Missing text")
            out = parse_ollama(content) if provider == "ollama" else parse(content)
            out = scope_rules(out, event["kind"])
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ClassifierError(f"{name} returned an invalid chat response. Retry or select another chat model.", code="invalid_provider_response") from None
        out.update(raw_response=content, validation_succeeded=out.get("verdict") in VERDICTS,
                   latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                   attempts=attempt + 1, retry_wait_ms=round(wait_seconds * 1000, 1),
                   prompt_tokens=usage.get("prompt_tokens", 0),
                   completion_tokens=usage.get("completion_tokens", 0), model=model, provider=provider)
        return out
    except httpx.TimeoutException:
        raise ClassifierError(f"{name} request timed out. Retry the classification.", 504, "provider_timeout") from None
    except httpx.RequestError:
        raise ClassifierError(f"Could not connect to {name}. Check internet access and proxy settings.", 503, "provider_connection_error") from None
    finally:
        if recovery_client is not None:
            recovery_client.close()
        if owned_client:
            client.close()