# Evaluation summary

## Run configuration

```json
{
  "experiment": "final_v3_dev_NVIDIA_A100_SXM4_40GB",
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
  "split": "dev",
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
  "started_at": "2026-11-08T11:26:43.536235+00:00",
  "finished_at": "2026-11-08T11:29:21.770214+00:00",
  "repository_commit": "71a629d4527fcd5e31d3779081a68084ffcd425c",
  "repository_dirty": false,
  "policy_sha256": "82c328d2f916c9dfed3a90fecd1c444673cb977501e5da639538441b51a44068",
  "prompt_sha256": "5e37728a7bd711596af4d15fdee543dd54d41091936bcc363cc135987a516b55",
  "dataset_sha256": "b308486d09ba0b9d643407cbb9c00ca375167a54474fb6a60f25b953ea88d862",
  "selected_case_ids": [
    "bd14d7cb07a1",
    "9f0969d6d997",
    "546fd18131d6",
    "84e8f8f0811e",
    "763cf87552ec",
    "c64f0ef2e375",
    "c3e1ab0faf61",
    "86956b5e87d8",
    "618bc5014e43",
    "985a399965cc",
    "1d76793c3890",
    "3f861dd98ffe",
    "905db815b5a1",
    "0800bf43c363",
    "f369508dba4b",
    "ecfed975097d",
    "657be9d48a4d",
    "8c1dbae26ee4",
    "ff7c9453be2e",
    "d9c96145218b",
    "0f66e02e0cd9",
    "8ac7536cf5d4",
    "3d34a506cb8d",
    "98b0505f664f",
    "c3069d488663",
    "b4f18e464702",
    "424872357ea4",
    "bcae054095c2",
    "4d7499907380",
    "2cb1a3ff9022",
    "f09420ec716b",
    "9c6ef38a3a1d",
    "f254cfc20a9b",
    "7c6f13fb853a",
    "5e3725d7a2a8",
    "8a367d299514",
    "ab893ab76fa3",
    "d5c4df5b5e49",
    "c53b85ea471f",
    "39c5c5505706",
    "d5ba2289d471",
    "314dc6dc31b0",
    "e1c8fc3213fe",
    "07a01cc175aa",
    "d0ccd82446ce",
    "21ce4debd512",
    "325cbf413228",
    "53d28579e920",
    "c2d47b56964a",
    "9b6830dad653",
    "4597d185ce56",
    "6297467d5d6a",
    "4dd6368db794",
    "e31b165db446",
    "09df3490b4a7",
    "68a37b1e648e",
    "7d48f99ed1d2",
    "dfef99a6bf05",
    "edbd11e22c7d",
    "17580d283749",
    "aabec1d3e16d",
    "629f6a839bb2",
    "6437283e0765",
    "5d6af5a993dc",
    "e18686f079e6",
    "89259a5f2219",
    "825e3228b9e7",
    "9a49796f416e",
    "25dbac4ea486",
    "edccfb4df70b",
    "0ab0fc824be1",
    "d9f21e2995f4",
    "7b92efe0b615",
    "9b1c8c422924",
    "c7c19ad5118e",
    "ae9ebec1e384",
    "7efa26e9e9f6",
    "d170277be075",
    "20a41513ed05",
    "59f84e4250ba",
    "d642990cbe22",
    "5dec5aba8d9e",
    "a10c47f30580",
    "7f7ed38b49d7",
    "a9c0ed55028b",
    "7a3c1f1e92d0",
    "7875a7cf0d46",
    "041bdcf57e56",
    "fd21ca09ded2",
    "9a09624de2ce",
    "4437f6142caa",
    "cceb102aeed7",
    "cdf5982b9c09",
    "c3225080e444",
    "a4361e1afbee",
    "b6a17b8b45ba",
    "a0b5d9c1d969",
    "2cefceefde75",
    "306bd1b8e741",
    "06188aa2fa6a",
    "0dc4f433b571",
    "f328064230ab",
    "5d1b94942ce0",
    "807351d1700f",
    "cc3d09b313a5"
  ],
  "status": "completed",
  "experiment_metadata": {
    "batch_id": "20261108T111953_eda8ec18",
    "prompt_version": "v3",
    "prompt_source_commit": "0901c79788bac98d090fa528ac0c5b35f947997c",
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
  "completed_cases": 105
}
```

## Metrics

Completed 105 / 105 selected cases.

- accuracy: 0.7714285714285715
- violation_recall: 0.8974358974358975
- unsafe_allow_rate: 0.07692307692307693
- false_block_rate: 0.2698412698412698
- escalation_recall: 0.0
- invalid_responses: 0

Accuracy includes invalid attempts as incorrect. Recall denominators include all completed gold cases. Unsafe allows = gold violations predicted allow / gold violations. False blocks = gold allows predicted violation or escalate / gold allows.

## Per-class metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| allow | 0.9387755102040817 | 0.7301587301587301 | 0.8214285714285714 | 63 |
| violation | 0.6481481481481481 | 0.8974358974358975 | 0.7526881720430108 | 39 |
| escalate | 0.0 | 0.0 | 0.0 | 3 |

## Confusion matrix (gold rows, predicted columns)

| Gold | allow | violation | escalate | invalid |
|---|---:|---:|---:|---:|
| allow | 46 | 16 | 1 | 0 |
| violation | 3 | 35 | 1 | 0 |
| escalate | 0 | 3 | 0 | 0 |

## Latency

all completed attempts, including failures; wall time including retries; nearest-rank percentiles

Measured cases: 105; missing cases: 0.

| Statistic | Milliseconds |
|---|---:|
| P50 | 1393.717 |
| P90 | 2165.488 |
| P95 | 2398.729 |
| P99 | 3931.191 |
| MEAN | 1505.1789714285712 |
| MIN | 736.552 |
| MAX | 5554.48 |
| TOTAL | 158043.792 |

Total is summed measured inference wall time, not full run duration or throughput. Small samples make tail percentiles unstable. Streaming time-to-first-token is not measured.

## Token usage

Provider-reported usage from returned responses only; unreported retry usage is excluded.

| Tokens | Measured cases | Missing cases | Total | Mean |
|---|---:|---:|---:|---:|
| prompt_tokens | 105 | 0 | 355254 | 3383.3714285714286 |
| completion_tokens | 105 | 0 | 20859 | 198.65714285714284 |

## Cost (USD)

User-supplied rates times returned usage. Excludes unreported retry usage, subscriptions, hardware, electricity and compute rental; not a bill.

Status: unavailable; priced cases: 0; observed-usage estimate: unavailable; all-cases estimate: unavailable.
Local Ollama has no Ollama token fee; hardware, electricity and rented compute costs are not measured. No cloud rate is inferred automatically from a model name.

## Error breakdown

Errors include wrong verdicts and invalid responses; grouped by gold annotation rule.

### event_kind

| Group | Cases | Errors | Invalid |
|---|---:|---:|---:|
| model_output | 29 | 6 | 0 |
| tool_call | 24 | 11 | 0 |
| tool_response | 31 | 4 | 0 |
| user_input | 21 | 3 | 0 |

### gold_policy_rule

| Group | Cases | Errors | Invalid |
|---|---:|---:|---:|
| R1 | 5 | 0 | 0 |
| R1,R4 | 5 | 0 | 0 |
| R2 | 7 | 0 | 0 |
| R2,R4 | 5 | 0 | 0 |
| R3 | 2 | 0 | 0 |
| R4 | 14 | 4 | 0 |
| R4,R5 | 1 | 0 | 0 |
| R5 | 3 | 3 | 0 |
| none | 63 | 17 | 0 |

