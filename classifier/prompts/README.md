# Frozen prompt versions

- `prompt_v1.py`: original baseline `SYSTEM`, commit `a2722bf`.
- `prompt_v2.py`: `SYSTEM` from `64f27df`, the version paired with deterministic rule scoping before `674adc8` removed that code.
- `prompt_v3.py`: final/current `SYSTEM`, commit `0901c79`.

Each module records the full source commit. Templates retain their exact historical runtime strings and `{policy}` placeholder. The final suite formats the selected policy into the original location, without appending a second policy. The package exports v3 as `SYSTEM`, so production imports remain compatible. Event-kind guidance and the Ollama classification instruction remain shared and unchanged.

The final experiments compare system prompts under the current inference pipeline. They do not restore earlier event rendering, response schema, parsing, policies, or deterministic verdict rewriting. In particular, v2's old Python rule filter could turn an out-of-scope violation into allow; that behavior is not reintroduced. The original baseline asks for different output ordering from the current schema; invalid responses are counted, not repaired. These runs are new frozen comparisons, not reproductions of historical scores.
