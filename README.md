# Policy Event Classifier for AI-agent traces

Classifies **one** agent trace event (`user_input`, `model_output`, `tool_call` or `tool_response`) against a written policy. It returns:
- **allow**, **violation** or **escalate** (a material fact is missing),
- the rules involved, the evidence, and the missing fact.

The model is a prompted local LLM (`qwen3:4b` via Ollama), with no fine-tuning.

**Start here:**
- [`WRITEUP.md`](WRITEUP.md): reasoning, assumptions, results, limitations.
- [`CORNER_CASES.md`](CORNER_CASES.md): what the policy does not decide.
- [`data/LABEL_DECISIONS.md`](data/LABEL_DECISIONS.md): how the labels were made.
- [`experiments/reports/final_A100_policy_v1_1/comparison.md`](experiments/reports/final_A100_policy_v1_1/comparison.md): final numbers with confidence intervals.

## Run it (one command)

Prerequisites: Python 3.13+, [uv](https://docs.astral.sh/uv/), Node.js + npm, [Ollama](https://ollama.com), and GNU Make (optional, see below).

```bash
uv sync --frozen
npm --prefix web ci
cp .env.example .env          # PowerShell: Copy-Item .env.example .env
ollama pull qwen3:4b
make run                      # no Make? use: uv run python scripts/run_app.py
```

`make run` does the following:
- Checks the configuration.
- Starts Ollama if it isn't running.
- Verifies the model is installed. If it isn't, it prints the `ollama pull` command; it never downloads silently.
- Starts the FastAPI backend (:8000) and the Vite frontend (:5173), and waits until both answer.

It runs **no** evaluation. Ctrl+C stops everything it started. Logs go to `.run/logs/`.

Open **http://127.0.0.1:5173**. Pick a demo case from the dropdown, or paste one JSON event, then click **Classify Event**. The page shows the verdict, rules, rationale and any missing fact. API docs are at http://127.0.0.1:8000/docs.

```json
{"kind": "tool_call", "tool": "send_email",
 "args": {"recipients": ["d.okafor@gmail.com"], "body": "Q3 revenue draft attached"},
 "context": {"original_request": "Summarize the Q3 report for the finance team.", "previous_events": []}}
```

The defaults are policy `policy_v1_1.md` and model `qwen3:4b`. To change them, edit `.env`: `POLICY_FILE`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `INFERENCE_PROVIDER`. Groq and Gemini adapters exist for the app; the evaluator is Ollama-only. Never commit API keys.

## Evaluate

```bash
# 105 dev cases, production prompt (v3), policy v1.1, 6 events of context
uv run python eval/run_eval.py --name my_dev_run

# position probes (separate 15-event set, not dev/test)
uv run python eval/run_eval.py --name probes --dataset data/position_probes.jsonl --split probe

# confidence intervals + paired McNemar over any folder of runs (no inference)
uv run python eval/stats.py experiments/reports/final_A100_policy_v1_1
```

Options: `--context 0|3|6|all`, `--model`, `--policy`, `--system-prompt <file>`, and `--split test`. Only use `--split test` for a planned, frozen held-out run.

Each run writes a new `results/<name>_<UTC timestamp>_<suffix>/` folder containing:
- `prompt.txt` and `policy.md`: the exact text used.
- `run_config.json`: model digest, generation parameters, dataset/prompt/policy SHA-256, git commit and dirty flag.
- `predictions.jsonl` and `failures.jsonl`: per case, with raw model output, latency and tokens.
- `metrics.json` and `summary.md`: accuracy, per-class P/R/F1, confusion matrix, violation recall, unsafe-allow and false-block rates, escalation recall, latency percentiles and token totals.

Invalid model output is counted as wrong, never repaired.

The final 3-prompt × dev+test batch was run in Colab on an A100 with [`experiments/colab_ollama_eval.ipynb`](experiments/colab_ollama_eval.ipynb) → [`eval/final_runs.py`](eval/final_runs.py). Its outputs are committed under `experiments/reports/final_A100_policy_v1_1/`.

## Data

| File | What it is |
|---|---|
| `data/dataset.jsonl` | 150 labelled events from AgentDojo: 105 dev, 45 test, trace-disjoint |
| `data/provenance.jsonl` | per-case source (agent model, suite, attack). Hidden from the classifier. |
| `data/position_probes.jsonl` | 15 hand-written probes, the same payloads across the 4 event kinds |
| `data/labeling/` | original labelling sheet (AI drafts plus my decisions), extraction notes |
| `scripts/extract_agentdojo.py` | regenerates the sample from AgentDojo `runs/` (see `data/labeling/EXTRACTION.md`) |

## Checks

```bash
uv run python -m pytest -q        # offline; HTTP is mocked, no model needed
npm --prefix web run build
```

## Layout

```text
classifier/core.py          request building, inference transport, JSON validation (shared by app and eval)
classifier/prompts/         frozen prompts v1, v2, v3 (v3 = production)
eval/run_eval.py            evaluator
eval/stats.py               confidence intervals and paired tests over saved runs
eval/final_runs.py          frozen 3-prompt batch used for the final results
server.py, web/             FastAPI + React demo
scripts/run_app.py          one-command supervisor (used by `make run`)
policy_v1.md, policy_v1_1.md, policy-v1-gaps.md
experiments/reports/        final and historical reports
experiments/notes/          working notes from development
tests/                      offline test suite
```

## Known limitations

See [WRITEUP.md, Limitations](WRITEUP.md#10-limitations). In short:
- Labels were AI-drafted, then audited by one person (me); there is no second annotator.
- n=45 test.
- Escalation is effectively untested (4 labels) and does not work.
- About 1.4 s P50 per event is too slow for inline gating of every event.
- The supervisor is for local review, not production. It has no auth, TLS or restart management.
