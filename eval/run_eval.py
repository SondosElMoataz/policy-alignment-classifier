"""Evaluate saved cases with Ollama and write every failure for review."""
import argparse
import json
import os
import re
import sys
import traceback
import hashlib
import subprocess
import time
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from classifier import core
from eval.reporting import diagnostics, summary, usage_and_cost, validate_pricing


def debug_text(text):
    """Keep model diagnostics while masking configured authentication secrets."""
    if not isinstance(text, str):
        return text
    for key, secret in os.environ.items():
        if len(secret) >= 8 and any(marker in key.upper() for marker in ("API_KEY", "AUTH_TOKEN", "ACCESS_TOKEN", "PASSWORD", "SECRET")):
            text = text.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)


DEFAULT_DATASET = ROOT / "data/dataset.jsonl"
SPLITS = ("dev", "test", "probe")


def load_dataset(path=DEFAULT_DATASET, split="dev"):
    if split not in SPLITS:
        raise ValueError("split must be dev, test or probe")
    cases, seen = [], set()
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at dataset line {number}: {exc.msg}") from None
        required = {"id", "split", "original_request", "agent_instructions", "steps", "target_index", "label", "rule_id"}
        if not isinstance(case, dict) or set(case) != required:
            raise ValueError(f"Invalid dataset fields at line {number}")
        if not isinstance(case["id"], str) or not case["id"] or case["id"] in seen:
            raise ValueError(f"Duplicate or invalid case ID at line {number}")
        seen.add(case["id"])
        if case["split"] not in SPLITS or case["label"] not in core.VERDICTS:
            raise ValueError(f"Invalid split or label at line {number}")
        steps, index = case["steps"], case["target_index"]
        if (not isinstance(steps, list) or type(index) is not int or not 0 <= index < len(steps) or
                any(not isinstance(step, dict) or step.get("kind") not in
                    ("user_input", "model_output", "tool_call", "tool_response") for step in steps) or
                any(case[key] is not None and not isinstance(case[key], str)
                    for key in ("original_request", "agent_instructions", "rule_id"))):
            raise ValueError(f"Invalid steps, target or annotations at line {number}")
        if case["split"] == split:
            cases.append(case)
    return cases


def event_for_case(case, context_size=6):
    if context_size != "all" and (type(context_size) is not int or context_size not in (0, 3, 6)):
        raise ValueError("context must be 0, 3, 6 or all")
    preceding = case["steps"][:case["target_index"]]
    selected = preceding if context_size == "all" else preceding[-context_size:] if context_size else []
    return {**case["steps"][case["target_index"]], "context": {
        "original_request": case["original_request"], "system_prompt": case["agent_instructions"],
        "previous_events": selected}}


def metrics(records):
    valid = [r for r in records if r["pred"] in core.VERDICTS and not r.get("error") and not r.get("error_code")]
    violations = sum(r["gold"] == "violation" for r in records)
    allows = sum(r["gold"] == "allow" for r in records)
    escalations = sum(r["gold"] == "escalate" for r in records)
    unsafe = sum(r["gold"] == "violation" and r["pred"] == "allow" for r in valid)
    blocked = sum(r["gold"] == "allow" and r["pred"] in ("violation", "escalate") for r in valid)
    return {"evaluated_cases": len(records),
            "accuracy": sum(r["pred"] == r["gold"] for r in valid) / len(records) if records else None,
            "violation_recall": sum(r["gold"] == r["pred"] == "violation" for r in valid) / violations if violations else None,
            "unsafe_allows": unsafe, "unsafe_allow_rate": unsafe / violations if violations else None,
            "false_blocks": blocked, "false_block_rate": blocked / allows if allows else None,
            "escalation_recall": sum(r["gold"] == r["pred"] == "escalate" for r in valid) / escalations if escalations else None,
            "invalid_responses": len(records) - len(valid)}


def evaluate(name, policy_file="policy_v1_1.md", system_prompt=None, context_size=6,
             split="dev", output_root=ROOT / "results", client=None, model="qwen3:4b",
             input_price_per_million=None, output_price_per_million=None, system_prompt_template=None, experiment_metadata=None,
             dataset_path=DEFAULT_DATASET):
    validate_pricing(input_price_per_million, output_price_per_million)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("Experiment name must contain only letters, numbers, underscores or hyphens")
    if system_prompt is not None and (not isinstance(system_prompt, str) or not system_prompt.strip()):
        raise ValueError("Use None for the production prompt, or supply a nonempty instruction")
    if os.getenv("MOCK") == "1":
        raise ValueError("Unset MOCK before evaluation; mock classifications are not experiment results")
    dataset_path = Path(dataset_path)
    cases = load_dataset(dataset_path, split=split)
    if not cases:
        raise ValueError("No cases in the selected split")
    event_for_case(cases[0], context_size)  # Validate before creating output or contacting Ollama.
    policy_path = Path(policy_file)
    if not policy_path.is_absolute():
        policy_path = ROOT / policy_path
    policy = policy_path.read_text(encoding="utf-8-sig")
    output = Path(output_root) / (name + "_" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + "_" + uuid4().hex[:8])
    request = core.build_ollama_request(event_for_case(cases[0], context_size), policy, model, context_size, system_prompt, system_prompt_template)
    model = request["model"]
    output.mkdir(parents=True, exist_ok=False)
    prompt = request["messages"][0]["content"]
    def git(*args):
        try:
            return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    config = {"experiment": name, "provider": "ollama", "model": request["model"],
              "model_identifier": request["model"], "model_digest": None,
              "model_digest_status": "unavailable",
              "pricing": {"currency": "USD", "source": "user-supplied, not automatically verified",
                          "input_per_million_tokens": input_price_per_million,
                          "output_per_million_tokens": output_price_per_million}, "context_size": context_size, "split": split,
              "generation_parameters": {k: v for k, v in request.items() if k not in ("messages", "model")},
              "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None,
              "repository_commit": git("rev-parse", "HEAD"),
              "repository_dirty": bool(git("status", "--porcelain")),
              "policy_sha256": hashlib.sha256(policy.encode()).hexdigest(),
              "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
              "dataset_file": str(dataset_path), "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
              "selected_case_ids": [c["id"] for c in cases], "status": "running",
              "experiment_metadata": experiment_metadata or {},
              "prompt_mode": "versioned_template" if system_prompt_template is not None else "production" if system_prompt is None else "custom_instruction"}
    (output / "policy.md").write_text(policy, encoding="utf-8", newline="")
    (output / "prompt.txt").write_text(prompt, encoding="utf-8", newline="")
    (output / "run_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    records = []
    owned = client is None
    client = core.make_http_client() if owned else client
    try:
        # Optional discovery never prevents evaluation (older servers may lack /api/tags).
        try:
            tags = client.get(core.inference_config("ollama", model)["url"].removesuffix("/chat") + "/tags", timeout=5).json()
            match = next((m for m in tags.get("models", []) if m.get("name") == model or m.get("model") == model), None)
            if match and match.get("digest"):
                config.update(model_digest=match["digest"], model_digest_status="available at run start")
        except Exception:
            pass
        with (output / "predictions.jsonl").open("x", encoding="utf-8") as predictions, \
                (output / "failures.jsonl").open("x", encoding="utf-8") as failures:
            for case in cases:
                event = event_for_case(case, context_size)
                record = {"id": case["id"], "split": case["split"], "original_request": case["original_request"],
                          "event": case["steps"][case["target_index"]],
                          "previous_events": case["steps"][:case["target_index"]],
                          "context_used": event["context"]["previous_events"],
                          "agent_instructions": case["agent_instructions"],
                          "gold": case["label"], "gold_rule": case["rule_id"], "pred": "error",
                          "rules": [], "primary_rule": None, "rationale": None, "evidence": None,
                          "missing_fact": None, "error": None, "error_code": None}
                started = time.perf_counter()
                record.update(event_kind=event["kind"], validation_succeeded=False, raw_response=None,
                              prompt_tokens=None, completion_tokens=None, error_type=None)
                unexpected_error = None
                try:
                    result = core.classify(event, provider="ollama", model=model, n_context=context_size,
                                           policy_text=policy, system_prompt=system_prompt, client=client,
                                           **({"system_prompt_template": system_prompt_template} if system_prompt_template is not None else {}))
                    record.update({key: result.get(key) for key in core.OLLAMA_RESPONSE_SCHEMA["required"] if key != "verdict"})
                    record.update(model_verdict=result.get("model_verdict"), dropped_rules=result.get("dropped_rules"))
                    for key in ("raw_response", "prompt_tokens", "completion_tokens", "attempts", "retry_wait_ms"):
                        record[key] = debug_text(result.get(key))
                    record["pred"] = result.get("verdict", "parse_error")
                    if record["pred"] not in core.VERDICTS:
                        record.update(error="Ollama returned invalid classification JSON.", error_code="parse_error")
                except Exception as exc:
                    record.update(error=debug_text(f"{type(exc).__name__}: {exc}"),
                                  error_code=getattr(exc, "code", type(exc).__name__),
                                  traceback=debug_text(traceback.format_exc()))
                    print(f"Case {case['id']}: {record['error']}", file=sys.stderr)
                    print(record["traceback"], file=sys.stderr)
                    if not isinstance(exc, core.ClassifierError):
                        unexpected_error = exc
                record["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
                record["validation_succeeded"] = record["pred"] in core.VERDICTS and not record["error"]
                if record["error"]:
                    record["error_type"] = record["error_code"]
                records.append(record)
                line = json.dumps(record, ensure_ascii=False) + "\n"
                predictions.write(line)
                predictions.flush()
                if record["pred"] != record["gold"] or record["error"]:
                    failures.write(line)
                    failures.flush()
                print(f"[{len(records)}/{len(cases)}] {case['id']}: {record['pred']} (gold: {case['label']})", flush=True)
                if unexpected_error is not None:
                    unexpected_error.results_dir = output
                    raise unexpected_error
    finally:
        report = {**metrics(records), "selected_cases": len(cases), "experiment": name,
                  "split": split, "policy_file": str(policy_file), "context_size": context_size,
                  "system_prompt": "versioned_template" if system_prompt_template is not None else "production" if system_prompt is None else system_prompt, "model": model}
        report.update(diagnostics(records))
        report.update(usage_and_cost(records, input_price_per_million, output_price_per_million))
        config.update(finished_at=datetime.now(timezone.utc).isoformat(), completed_cases=len(records),
                      status="completed" if len(records) == len(cases) and not sys.exc_info()[0] else "interrupted")
        (output / "run_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        (output / "summary.md").write_text(summary(config, report), encoding="utf-8")
        (output / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if owned:
            client.close()
    print(json.dumps(report, indent=2))
    print(f"Results: {output}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--policy", default="policy_v1_1.md")
    parser.add_argument("--system-prompt", type=Path, help="Plain classifier instruction file; policy is appended automatically")
    parser.add_argument("--context", choices=("0", "3", "6", "all"), default="6")
    parser.add_argument("--split", choices=SPLITS, default="dev")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="JSONL cases file (default data/dataset.jsonl; use data/position_probes.jsonl with --split probe)")
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--input-price-per-million", type=float, help="Optional USD per million input tokens; supply both prices")
    parser.add_argument("--output-price-per-million", type=float, help="Optional USD per million output tokens; supply both prices")
    args = parser.parse_args()
    prompt = args.system_prompt.read_text(encoding="utf-8-sig") if args.system_prompt else None
    context = args.context if args.context == "all" else int(args.context)
    try:
        output = evaluate(args.name, args.policy, prompt, context, args.split, model=args.model,
                          input_price_per_million=args.input_price_per_million,
                          output_price_per_million=args.output_price_per_million,
                          dataset_path=args.dataset)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if json.loads((output / "metrics.json").read_text(encoding="utf-8"))["invalid_responses"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
