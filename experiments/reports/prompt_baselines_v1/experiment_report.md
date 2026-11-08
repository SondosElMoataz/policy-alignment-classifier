# B0 / B1 / E1 / E2 experiment comparison

Primary metric: unsafe-allow rate. Provisional utility constraint: at most 6 false blocks on the frozen 23 allowed cases. This is not a validated safety threshold.

Hypotheses: B0 tests whether the longer production instruction adds value; E1 tests general evidence/verdict guidance; E2 tests authorization/trust-boundary guidance. B1 is the original reference.

Changed variables: B0 replaces only the system instruction; E1 appends general guidance; E2 reportedly appends authorization guidance (full prompt/config unavailable locally). Policy v1.0, Qwen3 4B, schema and generation settings are held fixed for the planned B0.

| Experiment | Evidence | Accuracy /50 | Unsafe allows /24 | Violation recall | False blocks /23 | Escalation recall /3 | Invalid |
|---|---|---:|---:|---:|---:|---:|---:|
| B0 | not run | unknown | unknown (unknown) | unknown | unknown (unknown) | unknown | unknown |
| B1 | verified predictions | 66.0% | 9 (37.5%) | 62.5% | 5 (21.7%) | 0.0% | 0 |
| E1 | derived saved log | 66.0% | 11 (45.8%) | 54.2% | 3 (13.0%) | 0.0% | 0 |
| E2 | user-reported aggregates | 64.0% | 9 (37.5%) | 58.3% | 5 (21.7%) | 0.0% | 1 |

## Decisions and regressions

- **B0: pending**. No inference run event-level comparison unavailable.
- **B1: reference**. Original working B1 baseline reference.
- **E1: reject**. No reduction in unsafe-allow rate versus B1 (9/24); investigate any invalid responses separately. 3 improvements, 3 regressions.
- **E2: reject**. No reduction in unsafe-allow rate versus B1 (9/24); investigate any invalid responses separately. event-level comparison unavailable.

E2 reportedly changed two valid decisions (one improved, one worsened), but their IDs/rationales and the invalid-response payload are unavailable. Investigate the invalid response; do not count 32/49 as all-case accuracy. E1 regressions and baseline rationales are listed in changed_decisions.csv; full E1 rationales were not saved locally.

## Metric definitions and limitations

Accuracy uses all 50 cases. Violation recall and unsafe-allow rate use all 24 gold violations. False blocks include violation OR escalation on the 23 gold allows. Escalation recall uses all 3 provisional escalation labels. Invalid responses, API failures and unfinished events remain incorrect in accuracy/recall; they are not silently counted as allows. Latency is p50/p95 over valid returned verdicts, excludes failures, and may be historical.

B1 latency is in comparison.json; E1 latency is approximate from rounded notebook logs; E2/B0 latency is unavailable. The supplied B1 reference is authoritative and agrees with archived predictions. B0 is not run. All labels remain unverified; the three escalation cases need review. No held-out evaluation, inference, significance claim, or historical-file modification was performed.
