# Data provenance

## AgentDojo traces (primary)
- Source: `runs/` in https://github.com/ethz-spylab/agentdojo (Debenedetti et al., NeurIPS 2024 D&B).
- Selected: 4 models (claude-3-7-sonnet-20250219, gpt-4o-2024-05-13, gemini-2.0-flash-001, Llama-3.3-70B-Instruct)
  × 3 suites (workspace, slack, banking) × 2 conditions (`none` = no attack, `important_instructions` = the strongest injection attack).
- 3,328 traces → 32,059 events (`raw_events.jsonl`, gitignored, 80 MB; regenerate below).
- `to_label.jsonl`: 150 events, stratified over suite × kind × injected-run × carries-injection, deduplicated by event text, seed 0.

**What's real and what isn't:** the agent behavior is real model output (actual tool calls, actual compliance with or resistance to injections). The users, companies and environment data are AgentDojo fixtures, not real people.

**Hidden fields:** anything under `_meta` is provenance for sampling and post-hoc analysis only. The classifier never sees it, and you should not look at it while labeling.

## Regenerate
```bash
git clone --depth 1 --filter=blob:none --no-checkout https://github.com/ethz-spylab/agentdojo /tmp/agentdojo
cd /tmp/agentdojo
python3 -c "ms=['claude-3-7-sonnet-20250219','gpt-4o-2024-05-13','gemini-2.0-flash-001','meta-llama_Llama-3.3-70B-Instruct'];print('\\n'.join(f'/runs/{m}/{s}/*/{a}/' for m in ms for s in ['workspace','slack','banking'] for a in ['none','important_instructions']))" > patterns.txt
git sparse-checkout set --no-cone --stdin < patterns.txt && git checkout
cd -
python scripts/extract_agentdojo.py --runs /tmp/agentdojo/runs --out data/raw_events.jsonl --sample 150 --sample-out data/to_label.jsonl --csv-out data/to_label.csv
```
