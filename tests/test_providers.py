"""Provider integration tests use HTTP mock transports only."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from classifier import core
import server


ENV = {"INFERENCE_PROVIDER": "groq", "GROQ_MODEL": "openai/gpt-oss-20b",
       "GEMINI_MODEL": "gemini-2.5-flash", "GROQ_API_KEY": "offline-groq",
       "GEMINI_API_KEY": "offline-gemini", "MOCK": "0", "POLICY_FILE": "policy_v1_1.md"}
EVENT = {"id": "example", "kind": "user_input", "content": "Summarize my inbox"}
ANSWER = {"verdict": "allow", "rules": [], "primary_rule": None,
          "rationale": "Ordinary request.", "evidence": "Summarize my inbox", "missing_fact": None}


def response():
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ANSWER)}}],
                                    "usage": {"prompt_tokens": 20, "completion_tokens": 10}})


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, ENV)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_provider_selection_defaults_overrides_and_invalid_options(self):
        self.assertEqual(core.inference_config()["model"], "openai/gpt-oss-20b")
        with patch.dict(os.environ, {"INFERENCE_PROVIDER": "gemini", "GEMINI_MODEL": ""}):
            self.assertEqual(core.inference_config()["model"], "gemini-2.5-flash")
            self.assertEqual(core.inference_config("groq")["url"], core.GROQ_URL)
            self.assertEqual(core.inference_config(model="custom")["model"], "custom")
        with self.assertRaises(ValueError):
            core.inference_config("unknown")
        with self.assertRaises(ValueError):
            core.inference_config("gemini", " ")

    def test_env_file_loading_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / ".env").write_text('INFERENCE_PROVIDER=gemini\nGEMINI_API_KEY="offline-file"\n', encoding="utf-8")
            with patch.object(core, "ROOT", path), patch.dict(os.environ):
                os.environ.pop("GEMINI_API_KEY")
                core.load_env()
                self.assertEqual(os.environ["GEMINI_API_KEY"], "offline-file")
                self.assertEqual(core.inference_config()["provider"], "groq")

    def test_request_format_and_parsing_for_both_providers(self):
        for provider, url, key in (("groq", core.GROQ_URL, "offline-groq"),
                                   ("gemini", core.GEMINI_URL, "offline-gemini")):
            with self.subTest(provider=provider):
                requests = []
                def handle(request):
                    requests.append(request)
                    return response()
                with httpx.Client(transport=httpx.MockTransport(handle)) as client:
                    result = core.classify(EVENT, provider=provider, client=client, policy_text="frozen policy", n_context=0)
                request = requests[0]
                payload = json.loads(request.content)
                self.assertEqual(str(request.url), url)
                self.assertEqual(request.headers["authorization"], "Bearer " + key)
                self.assertEqual(set(payload), {"model", "temperature", "response_format", "messages"})
                self.assertEqual(payload["response_format"], {"type": "json_object"})
                self.assertEqual(payload["messages"], [
                    {"role": "system", "content": core.SYSTEM.format(policy="frozen policy")},
                    {"role": "user", "content": core.render_event(EVENT, 0)}])
                for field, value in ANSWER.items():
                    self.assertEqual(result[field], value)
                self.assertEqual(result["provider"], provider)
                self.assertEqual(result["completion_tokens"], 10)
    def test_gemini_missing_key_and_errors_do_not_leak_response_or_credentials(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaises(core.ClassifierError) as caught:
                core.classify(EVENT, provider="gemini", policy_text="policy")
            self.assertEqual(caught.exception.code, "missing_api_key")
            self.assertIn("GEMINI_API_KEY", str(caught.exception))
        for status, code in ((400, "provider_error"), (401, "provider_auth_error"),
                             (403, "provider_auth_error"), (404, "model_not_found"),
                             (429, "rate_limit"), (503, "provider_unavailable")):
            with self.subTest(status=status), httpx.Client(transport=httpx.MockTransport(
                    lambda request: httpx.Response(status, json={"error": {"message": "offline-gemini secret content"}}))) as client:
                with self.assertRaises(core.ClassifierError) as caught:
                    core.classify(EVENT, provider="gemini", client=client, policy_text="policy", retries=0)
                self.assertEqual(caught.exception.code, code)
                self.assertIn("Gemini", str(caught.exception))
                self.assertNotIn("offline-gemini", str(caught.exception))

    def test_gemini_retry_info_and_retry_after(self):
        class Gate:
            def __init__(self):
                self.delays = []
            def defer(self, delay):
                self.delays.append(delay)
            def wait(self):
                return 0
        for headers, expected in (({}, 12.5), ({"retry-after": "30"}, 30)):
            gate = Gate()
            replies = iter([httpx.Response(429, headers=headers, json={"error": {"details": [
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "12.5s"}]}}), response()])
            with httpx.Client(transport=httpx.MockTransport(lambda request: next(replies))) as client:
                result = core.classify(EVENT, provider="gemini", client=client, policy_text="policy", rate_limit_gate=gate)
            self.assertEqual(gate.delays, [expected])
            self.assertEqual(result["attempts"], 2)

    def test_invalid_response_and_parse_error_semantics_preserved(self):
        for body, expected in (({"choices": []}, "invalid_provider_response"),
                               ({"choices": [{"message": {"content": None}}]}, "invalid_provider_response")):
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as client:
                with self.assertRaises(core.ClassifierError) as caught:
                    core.classify(EVENT, provider="gemini", client=client, policy_text="policy")
                self.assertEqual(caught.exception.code, expected)
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
                "choices": [{"message": {"content": "not json"}}]}))) as client:
            self.assertEqual(core.classify(EVENT, provider="gemini", client=client, policy_text="policy")["verdict"], "parse_error")

    def test_backend_uses_same_classifier_and_environment_as_evaluation(self):
        requests = []
        def handle(request):
            requests.append(json.loads(request.content))
            return response()
        with patch.dict(os.environ, {"INFERENCE_PROVIDER": "gemini"}), \
                httpx.Client(transport=httpx.MockTransport(handle)) as inference_client, \
                patch.object(server, "classify", side_effect=lambda event, **kwargs: core.classify(event, client=inference_client, **kwargs)), \
                TestClient(server.app) as app:
            metadata = app.get("/api/policy").json()
            self.assertEqual(metadata["default_provider"], "gemini")
            self.assertEqual(metadata["default_model"], "gemini-2.5-flash")
            result = app.post("/api/classify", json={"event": EVENT, "context": 6})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["provider"], "gemini")
            core.classify(EVENT, provider="gemini", model="gemini-2.5-flash", n_context=6,
                          policy_text=core.load_policy(), client=inference_client)
            self.assertEqual(requests[0], requests[1])
            self.assertEqual(app.post("/api/classify", json={"event": EVENT, "provider": "invalid"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
