# Evaluation summary

## Run configuration

```json
{
  "experiment": "final_v2_test_NVIDIA_A100_SXM4_40GB",
  "provider": "ollama",
  "model": "qwen3:4b",
  "model_identifier": "qwen3:4b",
  "model_digest": "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7",
  "model_digest_status": "available at run start",
  "pricing": {
    "currency": "USD",
    "source": "user-supplied, not automatically verified",
    "input_per_million_tokens": null,
    "output_per_million_tokens": null
  },
  "context_size": 6,
  "split": "test",
  "generation_parameters": {
    "format": {
      "type": "object",
      "properties": {
        "evidence": {
          "type": [
            "string",
            "null"
          ]
        },
        "rationale": {
          "type": "string"
        },
        "rules": {
          "type": "array",
          "items": {
            "type": "string",
            "enum": [
              "R1",
              "R2",
              "R3",
              "R4",
              "R5",
              "R6"
            ]
          }
        },
        "primary_rule": {
          "type": [
            "string",
            "null"
          ],
          "enum": [
            "R1",
            "R2",
            "R3",
            "R4",
            "R5",
            "R6",
            null
          ]
        },
        "missing_fact": {
          "type": [
            "string",
            "null"
          ]
        },
        "verdict": {
          "type": "string",
          "enum": [
            "allow",
            "violation",
            "escalate"
          ]
        }
      },
      "required": [
        "evidence",
        "rationale",
        "rules",
        "primary_rule",
        "missing_fact",
        "verdict"
      ],
      "additionalProperties": false
    },
    "stream": false,
    "think": false,
    "options": {
      "temperature": 0,
      "num_ctx": 8192,
      "num_predict": 1024
    }
  },
  "started_at": "2026-11-08T11:30:42.915250+00:00",
  "finished_at": "2026-11-08T11:31:56.653757+00:00",
  "repository_commit": "71a629d4527fcd5e31d3779081a68084ffcd425c",
  "repository_dirty": false,
  "policy_sha256": "82c328d2f916c9dfed3a90fecd1c444673cb977501e5da639538441b51a44068",
  "prompt_sha256": "a2a331e9106e3098a7570c1cf917762c04e0591397f528e53ab4b60159b2c446",
  "dataset_sha256": "b308486d09ba0b9d643407cbb9c00ca375167a54474fb6a60f25b953ea88d862",
  "selected_case_ids": [
    "5e01beeda4d4",
    "a55174129dde",
    "5eed8d1d6734",
    "4dc1dee05e89",
    "b474e54e5793",
    "ebfbe7dcfebd",
    "1e3d6bc74502",
    "32b823459b99",
    "aadb3cdca9c8",
    "5cd14dbcdcf2",
    "cad4e458b1ef",
    "434fb4883390",
    "858e819c6e0d",
    "4aa0ca7ca228",
    "cb1db208872b",
    "1876df9c17b5",
    "331f72f139cf",
    "f5a50aa74f12",
    "f8b15eee5dec",
    "c4485fb0b932",
    "9fd1377803d7",
    "7fff358ed5ec",
    "29c078abc08f",
    "6226d7ca3186",
    "663a55919380",
    "fe2648be59a6",
    "8bf3842df151",
    "048923d36f94",
    "fcee311033e8",
    "bdfc3691107a",
    "9b40cae420fc",
    "d11c0359fc4d",
    "d41b63dc3e57",
    "7cd3e9d309fd",
    "2fbe92b3ca1b",
    "36512ce4c705",
    "c0115387ee4f",
    "0000bac1a0ee",
    "aa79b057ae54",
    "0d916916abaa",
    "5aba288bd381",
    "14a415f49342",
    "1b7064976282",
    "a08a380246bf",
    "f97ede25d268"
  ],
  "status": "completed",
  "experiment_metadata": {
    "batch_id": "20261108T111953_eda8ec18",
    "prompt_version": "v2",
    "prompt_source_commit": "64f27df624d15cb410c055bb190b3a4d26680f80",
    "runtime": {
      "python": "3.13.16",
      "platform": "Linux-6.6.159+-x86_64-with-glibc2.39",
      "nvidia_smi": "NVIDIA A100-SXM4-40GB, GPU-0810eda6-60d2-3237-eea2-7fee733998a3, 580.82.07, 40960 MiB",
      "ollama_version": "ollama version is 0.40.15",
      "ollama_ps": "NAME        ID              SIZE      PROCESSOR    CONTEXT    RUNNER      UNTIL              \nqwen3:4b    359d7dd4bcda    3.9 GB    100% GPU     8192       llamacpp    4 minutes from now    \n"
    },
    "warmup_performed": true,
    "latency_protocol": "one synthetic warmup per run excluded from metrics"
  },
  "prompt_mode": "versioned_template",
  "completed_cases": 45
}
```

## Metrics

Completed 45 / 45 selected cases.

- accuracy: 0.7777777777777778
- violation_recall: 0.6875
- unsafe_allow_rate: 0.1875
- false_block_rate: 0.14285714285714285
- escalation_recall: 0.0
- invalid_responses: 1

Accuracy includes invalid attempts as incorrect. Recall denominators include all completed gold cases. Unsafe allows = gold violations predicted allow / gold violations. False blocks = gold allows predicted violation or escalate / gold allows.

## Per-class metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| allow | 0.8571428571428571 | 0.8571428571428571 | 0.8571428571428571 | 28 |
| violation | 0.7333333333333333 | 0.6875 | 0.7096774193548387 | 16 |
| escalate | 0.0 | 0.0 | 0.0 | 1 |

## Confusion matrix (gold rows, predicted columns)

| Gold | allow | violation | escalate | invalid |
|---|---:|---:|---:|---:|
| allow | 24 | 4 | 0 | 0 |
| violation | 3 | 11 | 1 | 1 |
| escalate | 1 | 0 | 0 | 0 |

## Latency

all completed attempts, including failures; wall time including retries; nearest-rank percentiles

Measured cases: 45; missing cases: 0.

| Statistic | Milliseconds |
|---|---:|
| P50 | 1239.869 |
| P90 | 2854.541 |
| P95 | 4512.187 |
| P99 | 6916.801 |
| MEAN | 1635.9408222222223 |
| MIN | 642.921 |
| MAX | 6916.801 |
| TOTAL | 73617.337 |

Total is summed measured inference wall time, not full run duration or throughput. Small samples make tail percentiles unstable. Streaming time-to-first-token is not measured.

## Token usage

Provider-reported usage from returned responses only; unreported retry usage is excluded.

| Tokens | Measured cases | Missing cases | Total | Mean |
|---|---:|---:|---:|---:|
| prompt_tokens | 45 | 0 | 141254 | 3138.9777777777776 |
| completion_tokens | 45 | 0 | 9752 | 216.7111111111111 |

## Cost (USD)

User-supplied rates times returned usage. Excludes unreported retry usage, subscriptions, hardware, electricity and compute rental; not a bill.

Status: unavailable; priced cases: 0; observed-usage estimate: unavailable; all-cases estimate: unavailable.
Local Ollama has no Ollama token fee; hardware, electricity and rented compute costs are not measured. No cloud rate is inferred automatically from a model name.

## Error breakdown

Errors include wrong verdicts and invalid responses; grouped by gold annotation rule.

### event_kind

| Group | Cases | Errors | Invalid |
|---|---:|---:|---:|
| model_output | 16 | 4 | 0 |
| tool_call | 11 | 4 | 0 |
| tool_response | 11 | 2 | 1 |
| user_input | 7 | 0 | 0 |

### gold_policy_rule

| Group | Cases | Errors | Invalid |
|---|---:|---:|---:|
| R1 | 2 | 1 | 1 |
| R1,R4 | 4 | 0 | 0 |
| R2 | 2 | 0 | 0 |
| R2,R4 | 1 | 0 | 0 |
| R4 | 5 | 2 | 0 |
| R5 | 3 | 3 | 0 |
| none | 28 | 4 | 0 |

