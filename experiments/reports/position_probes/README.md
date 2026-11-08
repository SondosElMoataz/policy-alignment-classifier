# Position probes

15 hand-written events from `data/position_probes.jsonl`, run once per frozen prompt (v1, v2, v3) with policy v1.1 and local `qwen3:4b` (digest `359d7dd4…`, the same as the A100 batch). They are separate from dev and test. They were run on a local machine, so the latency figures are not comparable with the A100 runs. The results table and interpretation are in [`WRITEUP.md`](../../../WRITEUP.md#position-probe).

Reproduce: `uv run python eval/run_eval.py --name probes --dataset data/position_probes.jsonl --split probe`. That runs the production prompt; `eval/final_runs.py` shows how to pass the frozen v1/v2 templates.
