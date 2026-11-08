"""Offline evaluator, failure artifacts, metrics and API regressions."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from classifier import core
from eval import run_eval
import server

ANSWER = {"verdict": "allow", "rules": [], "primary_rule": None, "rationale": "Allowed.",
          "evidence": None, "missing_fact": None}
CASE = {"id": "case-one", "split": "dev", "original_request": "Read the report.",
        "agent_instructions": "Use supplied tools.", "label": "allow", "rule_id": None,
        "steps": [{"kind": "user_input", "content": "PAST"},
                  {"kind": "tool_call", "tool": "lookup", "args": {}},
                  {"kind": "tool_response", "content": "FUTURE"}], "target_index": 1}


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"MOCK": "0", "POLICY_FILE": "policy_v1_1.md"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_metrics_include_errors_and_keep_escalation_distinct(self):
        records = [{"gold": gold, "pred": pred} for gold, pred in
                   (("allow", "allow"), ("violation", "violation"), ("escalate", "escalate"),
                    ("violation", "allow"), ("allow", "escalate"), ("escalate", "violation"),
                    ("violation", "parse_error"), ("allow", "error"))]
        result = run_eval.metrics(records)
        self.assertEqual(result["accuracy"], 3/8)
        self.assertEqual(result["violation_recall"], 1/3)
        self.assertEqual(result["unsafe_allows"], 1)
        self.assertEqual(result["false_blocks"], 1)
        self.assertEqual(result["escalation_recall"], 1/2)
        self.assertEqual(result["invalid_responses"], 2)
        self.assertIsNone(run_eval.metrics([])["accuracy"])
        self.assertIsNone(run_eval.metrics([{"gold": "allow", "pred": "allow"}])["violation_recall"])

    def test_every_wrong_or_invalid_case_is_saved_with_complete_review_context(self):
        cases = [{**CASE, "id": f"case-{i}", "label": gold, "rule_id": "R1" if gold != "allow" else None}
                 for i, gold in enumerate(("allow", "violation", "allow", "escalate", "violation", "allow"))]
        results = [ANSWER, ANSWER, {**ANSWER, "verdict": "escalate", "missing_fact": "Was it authorized?"},
                   {**ANSWER, "verdict": "violation", "rules": ["R1"], "primary_rule": "R1"},
                   {"verdict": "parse_error"}, core.ClassifierError("Ollama unavailable", code="provider_unavailable")]
        with tempfile.TemporaryDirectory() as directory, patch.object(run_eval, "load_dataset", return_value=cases) as load, \
                patch.object(core, "classify", side_effect=results), contextlib.redirect_stdout(io.StringIO()):
            with httpx.Client(transport=httpx.MockTransport(lambda request: self.fail("No live API"))) as client:
                output = run_eval.evaluate("failure_review", output_root=directory, client=client)
            load.assert_called_once_with(run_eval.DEFAULT_DATASET, split="dev")
            predictions = list(map(json.loads, (output / "predictions.jsonl").read_text().splitlines()))
            failures = list(map(json.loads, (output / "failures.jsonl").read_text().splitlines()))
            self.assertEqual(len(predictions), 6)
            self.assertEqual(failures, predictions[1:])
            self.assertEqual({p.name for p in output.iterdir()}, {"predictions.jsonl", "failures.jsonl", "metrics.json", "run_config.json", "prompt.txt", "policy.md", "summary.md"})
            for case, record in zip(cases, predictions):
                self.assertEqual(record["original_request"], case["original_request"])
                self.assertEqual(record["event"], case["steps"][1])
                self.assertEqual(record["previous_events"], case["steps"][:1])
                self.assertEqual(record["context_used"], case["steps"][:1])
                self.assertEqual(record["gold_rule"], case["rule_id"])
                self.assertNotIn("FUTURE", json.dumps(record))
            self.assertEqual(failures[1]["missing_fact"], "Was it authorized?")
            self.assertEqual(failures[-1]["error_code"], "provider_unavailable")
            self.assertEqual(failures[-2]["error_code"], "parse_error")
            metrics = json.loads((output / "metrics.json").read_text())
            self.assertEqual(metrics["invalid_responses"], 2)
            self.assertEqual(metrics["accuracy"], 1/6)
            self.assertEqual(metrics["selected_cases"], 6)

    def test_real_request_path_uses_shared_classifier_and_custom_prompt_with_full_policy(self):
        requests = []
        def respond(request):
            if request.method == "GET":
                return httpx.Response(200, json={"models": []})
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(ANSWER)}})
        with tempfile.TemporaryDirectory() as directory, patch.object(run_eval, "load_dataset", return_value=[CASE]), \
                httpx.Client(transport=httpx.MockTransport(respond)) as client, contextlib.redirect_stdout(io.StringIO()):
            first = run_eval.evaluate("production", output_root=directory, client=client)
            second = run_eval.evaluate("minimal", system_prompt='Classify this event. Return JSON {"verdict": ...}.',
                                       output_root=directory, client=client)
            import hashlib
            for output, request in zip((first, second), requests):
                prompt = (output / "prompt.txt").read_text(encoding="utf-8")
                policy = (output / "policy.md").read_text(encoding="utf-8")
                config = json.loads((output / "run_config.json").read_text())
                self.assertEqual(prompt, request["messages"][0]["content"])
                self.assertEqual(policy, core.load_policy())
                self.assertEqual(config["prompt_sha256"], hashlib.sha256(prompt.encode()).hexdigest())
                self.assertEqual(config["policy_sha256"], hashlib.sha256(policy.encode()).hexdigest())
                self.assertEqual(config["generation_parameters"], {k:v for k,v in request.items() if k not in ("model", "messages")})
                self.assertEqual(config["status"], "completed")
                report = json.loads((output / "metrics.json").read_text())
                self.assertEqual(report["confusion_matrix"]["allow"]["allow"], 1)
                self.assertEqual(report["per_class"]["allow"]["f1"], 1)
                self.assertIn("P95", (output / "summary.md").read_text())
                record = json.loads((output / "predictions.jsonl").read_text())
                self.assertTrue(record["validation_succeeded"])
                self.assertEqual(json.loads(record["raw_response"]), ANSWER)
                self.assertIsNone(record["prompt_tokens"])
            self.assertFalse(client.is_closed)
            self.assertNotEqual(first, second)
            self.assertEqual((second / "failures.jsonl").read_text(), "")
        baseline = core.build_ollama_request(run_eval.event_for_case(CASE), core.load_policy(), model="qwen3:4b")
        self.assertEqual(requests[0], baseline)
        self.assertNotEqual(requests[0]["messages"][0], requests[1]["messages"][0])
        self.assertIn(core.load_policy(), requests[1]["messages"][0]["content"])
        requests[0]["messages"][0] = requests[1]["messages"][0]
        self.assertEqual(requests[0], requests[1])

    def test_invalid_configuration_is_rejected_before_network_or_output(self):
        for change in ({"name": "../escape"}, {"context_size": 2}, {"system_prompt": ""}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory, \
                    patch.object(core, "make_http_client", side_effect=AssertionError("No API")):
                with self.assertRaises(ValueError):
                    run_eval.evaluate(**{"name": "test", "output_root": directory, **change})
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_stale_classifier_typeerror_is_visible_saved_and_stops_after_first_case(self):
        def stale_classify(event, provider=None, model=None, n_context=6, policy_text=None, client=None):
            self.fail("The incompatible signature must fail before inference")
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(run_eval, "load_dataset", return_value=[CASE, {**CASE, "id": "case-two"}]), \
                patch.object(core, "classify", side_effect=stale_classify) as classify, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
            with self.assertRaisesRegex(TypeError, "unexpected keyword argument 'system_prompt'"):
                run_eval.evaluate("stale_classifier", output_root=directory, client=object())
            self.assertEqual(classify.call_count, 1)
            output = next(Path(directory).iterdir())
            record = json.loads((output / "failures.jsonl").read_text())
            self.assertEqual(record["error_code"], "TypeError")
            self.assertIn("unexpected keyword argument 'system_prompt'", record["error"])
            self.assertIn("Traceback", record["traceback"])
            self.assertIn("unexpected keyword argument 'system_prompt'", errors.getvalue())
            self.assertEqual(json.loads((output / "metrics.json").read_text())["evaluated_cases"], 1)

    def test_api_loads_policy_automatically_and_preserves_missing_context_escalation(self):
        event = {"kind": "tool_call", "tool": "send_email", "args": {}}
        answer = {**ANSWER, "verdict": "escalate", "missing_fact": "Was this authorized?"}
        with TestClient(server.app) as app, patch.object(server, "classify", return_value=answer) as classify:
            response = app.post("/api/classify", json={"event": event})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["missing_fact"], "Was this authorized?")
            self.assertEqual(classify.call_args.args, (event,))
            self.assertEqual(classify.call_args.kwargs["policy_text"], core.load_policy())
            self.assertNotIn("context", event)
            self.assertEqual(app.post("/api/classify", json={"event": {"kind": "unknown"}}).status_code, 400)
        with TestClient(server.app) as app, patch.object(server, "classify", return_value={"verdict": "parse_error"}):
            self.assertEqual(app.post("/api/classify", json={"event": event}).status_code, 502)
        with TestClient(server.app) as app, patch.object(server, "classify", side_effect=core.ClassifierError("Unavailable", 503)):
            self.assertEqual(app.post("/api/classify", json={"event": event}).status_code, 503)

    def test_notebook_displays_every_failure_even_when_evaluation_raises(self):
        import sys
        import types
        notebook = json.loads((run_eval.ROOT / 'experiments/colab_ollama_eval.ipynb').read_text(encoding='utf-8'))
        source = ''.join(notebook['cells'][-1]['source'])
        failures = [{'id': 'wrong-case', 'gold': 'violation', 'pred': 'allow', 'rationale': 'Model explanation'},
                    {'id': 'invalid-case', 'gold': 'allow', 'pred': 'error', 'error': 'TypeError: full details'}]
        for stopped in (False, True):
            with self.subTest(stopped=stopped), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                (output / 'metrics.json').write_text('{"evaluated_cases": 2}')
                (output / 'failures.jsonl').write_text('\n'.join(map(json.dumps, failures)))
                def evaluate(*args, **kwargs):
                    if stopped:
                        error = TypeError('integration error')
                        error.results_dir = output
                        raise error
                    return output
                shown = []
                display_module = types.ModuleType('IPython.display')
                display_module.display = shown.append
                display_module.JSON = lambda data, **kwargs: data
                def run_suite(**kwargs):
                    try:
                        return evaluate()
                    except Exception as exc:
                        if getattr(exc, 'results_dir', None):
                            kwargs['on_result'](exc.results_dir)
                        raise
                    finally:
                        if not stopped:
                            kwargs['on_result'](output)
                namespace = dict(run_final_suite=run_suite, json=json, EXPERIMENT_PREFIX='test',
                                 POLICY_FILE='policy_v1.md', SPLITS=('dev',), CONTEXT_SIZE=6,
                                 MODEL='qwen3:4b', WARMUP=False, OUTPUT_ROOT=directory, HARDWARE={})
                with patch.dict(sys.modules, {'IPython.display': display_module}), \
                        contextlib.redirect_stdout(io.StringIO()) as text:
                    if stopped:
                        with self.assertRaises(TypeError):
                            exec(compile(source, 'notebook-results', 'exec'), namespace)
                    else:
                        namespace['run_final_suite'] = lambda **kw: (kw['on_result'](output) or output)
                        exec(compile(source, 'notebook-results', 'exec'), namespace)
                self.assertEqual(shown[1:], failures)
                self.assertIn('Failed or invalid cases: 2', text.getvalue())
                self.assertIn('Gold: violation | Predicted: allow', text.getvalue())
                self.assertIn('TypeError: full details', text.getvalue())

    def test_api_samples_use_only_dev_cases_from_the_single_dataset(self):
        with TestClient(server.app) as app, patch("httpx.Client", side_effect=AssertionError("No model calls")):
            samples = app.get("/api/samples").json()
            self.assertEqual(len(samples), 105)
            self.assertEqual({s["id"] for s in samples}, {c["id"] for c in run_eval.load_dataset()})
            self.assertEqual(app.get("/api/runtime").status_code, 200)


if __name__ == "__main__":
    unittest.main()
