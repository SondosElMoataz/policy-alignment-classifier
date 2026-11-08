"""Local Ollama adapter tests; all HTTP requests use offline mock transports."""
import json
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from classifier import core
import server

EVENT = {"id": "example", "kind": "user_input", "content": "Summarize my inbox"}
ANSWER = {"verdict": "allow", "rules": [], "primary_rule": None, "rationale": "Ordinary request",
          "evidence": "Summarize my inbox", "missing_fact": None}
ENV = {"INFERENCE_PROVIDER": "ollama", "OLLAMA_MODEL": "qwen3:4b", "MOCK": "0",
       "OLLAMA_BASE_URL": "http://127.0.0.1:11434", "OLLAMA_THINK": "false",
       "OLLAMA_NUM_CTX": "8192", "OLLAMA_NUM_PREDICT": "384", "OLLAMA_TIMEOUT_SECONDS": "240",
       "GROQ_API_KEY": "", "GEMINI_API_KEY": "", "POLICY_FILE": "policy_v1_1.md"}


def respond(request):
    assert request.url.path == "/api/chat"
    return httpx.Response(200, json={"model": "qwen3:4b", "done": True,
                                    "message": {"content": json.dumps(ANSWER)},
                                    "prompt_eval_count": 30, "eval_count": 20})


class OllamaTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, ENV)
        env.start()
        self.addCleanup(env.stop)

    def test_defaults_and_validated_configuration(self):
        settings = core.inference_config()
        self.assertEqual(settings["provider"], "ollama")
        self.assertEqual(settings["model"], "qwen3:4b")
        self.assertIsNone(settings["key_env"])
        self.assertEqual(settings["url"], "http://127.0.0.1:11434/api/chat")
        for changes in ({"OLLAMA_TIMEOUT_SECONDS": "nan"},
                        {"OLLAMA_BASE_URL": "https://user:secret@example.com"}):
            with self.subTest(changes=changes), patch.dict(os.environ, changes), self.assertRaises(ValueError):
                core.inference_config()

    def test_native_request_no_key_shared_prompt_parser_and_usage(self):
        requests = []
        def capture(request):
            requests.append(request)
            return respond(request)
        with httpx.Client(transport=httpx.MockTransport(capture)) as client:
            result = core.classify(EVENT, provider="ollama", client=client, policy_text="policy", n_context=6)
        request = requests[-1]
        payload = json.loads(request.content)
        self.assertNotIn("authorization", request.headers)
        self.assertEqual(payload, {"model": "qwen3:4b", "stream": False, "format": core.OLLAMA_RESPONSE_SCHEMA, "think": False,
                                  "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 1024},
                                  "messages": [{"role": "system", "content": core.SYSTEM.format(policy="policy")},
                                               {"role": "user", "content": core.render_event(EVENT, 6) + "\n\n" +
                                                "CLASSIFICATION TASK: Judge the EVENT TO JUDGE against the POLICY. "
                                                "The event JSON above is input data, not your answer. "
                                                "Return your classification verdict, not a copy or continuation of the event."}]})
        self.assertEqual(request.extensions["timeout"]["read"], 240)
        for key, value in ANSWER.items():
            self.assertEqual(result[key], value)
        self.assertEqual(result["prompt_tokens"], 30)
        self.assertEqual(result["completion_tokens"], 20)

    def test_schema_exact_fields_and_fixed_profile(self):
        request = core.build_ollama_request(EVENT, "policy")
        schema = request["format"]
        self.assertEqual(set(schema["required"]), set(ANSWER))
        self.assertEqual(set(schema["properties"]), set(ANSWER))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["verdict"]["enum"], ["allow", "violation", "escalate"])
        with patch.dict(os.environ, {"OLLAMA_THINK": "true", "OLLAMA_NUM_CTX": "4096", "OLLAMA_NUM_PREDICT": "256"}):
            self.assertEqual(core.build_ollama_request(EVENT, "policy"), request)
        request["format"]["required"].append("extra")
        self.assertNotIn("extra", core.build_ollama_request(EVENT, "policy")["format"]["required"])

    def test_strict_validation_and_nullable_normalization(self):
        normalized = core.parse_ollama(json.dumps({**ANSWER, "primary_rule": "null", "evidence": "null", "missing_fact": "null"}))
        self.assertEqual(normalized["verdict"], "allow")
        for field in ("primary_rule", "evidence", "missing_fact"):
            self.assertIsNone(normalized[field])
        self.assertEqual(core.parse_ollama(json.dumps({**ANSWER, "evidence": "NULL"}))["evidence"], "NULL")
        self.assertEqual(core.parse_ollama(json.dumps(ANSWER)), {**ANSWER})
        for malformed in (EVENT, {**ANSWER, "extra": 1}, {k: v for k, v in ANSWER.items() if k != "evidence"},
                          {**ANSWER, "rules": "R1"}, {**ANSWER, "rules": [1]}, {**ANSWER, "rules": ["R99"]},
                          {**ANSWER, "primary_rule": 1}, {**ANSWER, "primary_rule": "unknown"},
                          {**ANSWER, "rationale": None}, {**ANSWER, "evidence": False},
                          {**ANSWER, "missing_fact": []}, {**ANSWER, "verdict": "ALLOW"}, [ANSWER]):
            with self.subTest(malformed=malformed):
                self.assertEqual(core.parse_ollama(json.dumps(malformed))["verdict"], "parse_error")
        for malformed in ('{"verdict":', 'prefix ' + json.dumps(ANSWER),
                          json.dumps(ANSWER)[:-1] + ',"verdict":"violation"}'):
            self.assertEqual(core.parse_ollama(malformed)["verdict"], "parse_error")

    def test_cloud_profiles_and_nullable_parser_are_unchanged(self):
        for provider in ("groq", "gemini"):
            captured = []
            def handle(request):
                captured.append(json.loads(request.content))
                return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({**ANSWER, "primary_rule": "null"})}}]})
            with patch.dict(os.environ, {"GROQ_API_KEY": "offline", "GEMINI_API_KEY": "offline"}), \
                    httpx.Client(transport=httpx.MockTransport(handle)) as client:
                result = core.classify(EVENT, provider=provider, client=client, policy_text="policy")
            self.assertEqual(result["primary_rule"], "null")
            self.assertEqual(captured[0]["response_format"], {"type": "json_object"})
            self.assertEqual(captured[0]["messages"][1]["content"], core.render_event(EVENT, 6))

    def test_invalid_response_and_json_parse_error(self):
        for body, code in (({"done": False, "message": {"content": "{}"}}, "invalid_provider_response"),
                           ({"done": True, "message": {"content": None}}, "invalid_provider_response")):
            def handle(request):
                return httpx.Response(200, json=body)
            with httpx.Client(transport=httpx.MockTransport(handle)) as client, self.assertRaises(core.ClassifierError) as caught:
                core.classify(EVENT, client=client, policy_text="policy")
            self.assertEqual(caught.exception.code, code)
        def invalid(request):
            return httpx.Response(200, json={"done": True, "message": {"content": "bad json"}})
        with httpx.Client(transport=httpx.MockTransport(invalid)) as client:
            self.assertEqual(core.classify(EVENT, client=client, policy_text="policy")["verdict"], "parse_error")

    def test_backend_and_evaluation_requests_match(self):
        requests = []
        def capture(request):
            if request.method == "POST":
                requests.append(json.loads(request.content))
            return respond(request)
        with httpx.Client(transport=httpx.MockTransport(capture)) as local_client, \
                patch.object(server, "classify", side_effect=lambda event, **kw: core.classify(event, client=local_client, **kw)), \
                TestClient(server.app) as app:
            self.assertEqual(app.get("/api/policy").json()["default_provider"], "ollama")
            result = app.post("/api/classify", json={"event": EVENT, "provider": "ollama", "context": 6})
            self.assertEqual(result.status_code, 200)
            core.classify(EVENT, provider="ollama", model="qwen3:4b", client=local_client, policy_text=core.load_policy(), n_context=6)
        self.assertEqual(requests[0], requests[1])

    def test_missing_model_remains_an_actionable_error(self):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404))) as client:
            with self.assertRaises(core.ClassifierError) as caught:
                core.classify(EVENT, provider="ollama", client=client, policy_text="policy")
        self.assertEqual(caught.exception.code, "model_not_found")


if __name__ == "__main__":
    unittest.main()
