"""Dataset integrity and context selection; no inference."""
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from classifier import core
from eval.run_eval import ROOT, event_for_case, load_dataset


class DatasetTests(unittest.TestCase):
    def test_all_150_cases_and_labels_are_preserved_with_explicit_splits(self):
        dev = load_dataset()
        test = load_dataset(split="test")
        self.assertEqual(len(dev), 105)
        self.assertEqual(len(test), 45)
        self.assertEqual(len({c["id"] for c in dev + test}), 150)
        self.assertEqual(Counter(c["label"] for c in dev), {"allow": 63, "violation": 39, "escalate": 3})
        self.assertEqual(Counter(c["label"] for c in test), {"allow": 28, "violation": 16, "escalate": 1})
        self.assertFalse({c["id"] for c in dev} & {c["id"] for c in test})
        self.assertEqual(sum(c["original_request"] is None for c in dev + test), 28)
        self.assertNotIn("agentdojo", json.dumps(dev + test).lower())
        for case in dev + test:
            self.assertIn(case["steps"][case["target_index"]]["kind"], ("user_input", "model_output", "tool_call", "tool_response"))
            self.assertNotIn("label", event_for_case(case))

    def test_context_is_derived_from_preceding_steps_and_never_future_steps(self):
        case = {"steps": [{"kind": "model_output", "content": f"PAST_{i}"} for i in range(25)] +
                         [{"kind": "tool_call", "tool": "lookup", "args": {}},
                          {"kind": "tool_response", "content": "FUTURE_SENTINEL"}],
                "target_index": 25, "original_request": "ORIGINAL_SENTINEL", "agent_instructions": "AGENT_SENTINEL"}
        for size, count in ((0, 0), (3, 3), (6, 6), ("all", 25)):
            with self.subTest(size=size):
                event = event_for_case(case, size)
                self.assertEqual(len(event["context"]["previous_events"]), count)
                self.assertEqual(event["context"]["previous_events"], case["steps"][25-count:25])
                rendered = core.build_ollama_request(event, "policy", n_context=size)["messages"][1]["content"]
                self.assertNotIn("FUTURE_SENTINEL", rendered)
                self.assertIn("ORIGINAL_SENTINEL", rendered)
                self.assertEqual("AGENT_SENTINEL" in rendered, bool(size))
        for invalid in (-1, 2, 20, True, "6", 3.0):
            with self.assertRaises(ValueError):
                event_for_case(case, invalid)

    def test_invalid_records_are_rejected_without_relabeling_or_resplitting(self):
        case = load_dataset()[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.jsonl"
            for change in ({"label": "unsure"}, {"split": "all"}, {"target_index": -1},
                           {"target_index": len(case["steps"])}, {"steps": []}, {"id": ""},
                           {"steps": [{"kind": "unknown"}]}, {"agent_instructions": []}):
                with self.subTest(change=change):
                    path.write_text(json.dumps({**case, **change}), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_dataset(path)
            path.write_text(json.dumps(case) + "\n" + json.dumps(case), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_dataset(path)
        with self.assertRaises(ValueError):
            load_dataset(split="all")

    def test_notebook_has_final_suite_inputs_and_uses_the_only_evaluator(self):
        notebook = json.loads((ROOT / "experiments/colab_ollama_eval.ipynb").read_text(encoding="utf-8"))
        cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
        import ast
        inputs = ast.parse("".join(cells[0]["source"]))
        self.assertEqual([n.targets[0].id for n in inputs.body],
                         ["SPLITS", "POLICY_FILE", "CONTEXT_SIZE", "MODEL", "EXPERIMENT_PREFIX", "WARMUP", "OUTPUT_ROOT"])
        source = "\n".join("".join(c["source"]) for c in cells)
        self.assertIn("from eval.run_eval import evaluate", source)
        self.assertIn('"failures.jsonl"', source)
        for i, cell in enumerate(cells):
            compile("".join(cell["source"]), f"cell-{i}", "exec")


if __name__ == "__main__":
    unittest.main()
