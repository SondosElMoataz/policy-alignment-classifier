"""Offline reporting only; no inference or changes to classifier decisions."""
import math
import json
from classifier.core import VERDICTS


def validate_pricing(input_price, output_price):
    if (input_price is None) != (output_price is None):
        raise ValueError("Supply both input and output USD prices per million tokens, or neither")
    if input_price is not None and any(type(v) not in (int, float) or not math.isfinite(v) or v < 0
                                       for v in (input_price, output_price)):
        raise ValueError("Token prices must be finite, nonnegative numbers")


def usage_and_cost(records, input_price=None, output_price=None):
    validate_pricing(input_price, output_price)
    usage = {}
    for field in ('prompt_tokens', 'completion_tokens'):
        counts = [r[field] for r in records if type(r.get(field)) is int and r[field] >= 0]
        usage[field] = {'measured_cases': len(counts), 'missing_cases': len(records) - len(counts),
                        'total': sum(counts) if counts else None,
                        'mean': sum(counts) / len(counts) if counts else None}
    complete = [r for r in records if all(type(r.get(f)) is int and r[f] >= 0
                                         for f in ('prompt_tokens', 'completion_tokens'))]
    observed = sum((r['prompt_tokens'] * input_price + r['completion_tokens'] * output_price) / 1_000_000
                   for r in complete) if input_price is not None and complete else None
    return {'token_usage': usage,
            'cost_usd': {'status': 'unavailable' if observed is None else 'estimated',
                         'input_per_million_tokens': input_price, 'output_per_million_tokens': output_price,
                         'priced_cases': len(complete) if input_price is not None else 0,
                         'observed_usage_estimate': observed,
                         'all_cases_estimate': observed if len(complete) == len(records) else None,
                         'basis': 'User-supplied rates times returned usage. Excludes unreported retry usage, subscriptions, hardware, electricity and compute rental; not a bill.'}}


def diagnostics(records):
    matrix = {g: {p: 0 for p in (*VERDICTS, 'invalid')} for g in VERDICTS}
    groups = {'event_kind': {}, 'gold_policy_rule': {}}
    for r in records:
        valid = r['pred'] in VERDICTS and not r.get('error') and not r.get('error_code')
        matrix[r['gold']][r['pred'] if valid else 'invalid'] += 1
        for dimension, key in [('event_kind', r['event']['kind']), ('gold_policy_rule', r.get('gold_rule') or 'none')]:
            item = groups[dimension].setdefault(key, {'cases': 0, 'errors': 0, 'invalid': 0})
            item['cases'] += 1
            item['errors'] += int(not valid or r['pred'] != r['gold'])
            item['invalid'] += int(not valid)
    classes = {}
    for label in VERDICTS:
        tp = matrix[label][label]
        support = sum(matrix[label].values())
        predicted = sum(matrix[g][label] for g in VERDICTS)
        classes[label] = {'precision': tp / predicted if predicted else None,
                          'recall': tp / support if support else None,
                          'f1': 2 * tp / (support + predicted) if support + predicted else None,
                          'support': support}
    times = sorted(r['latency_ms'] for r in records if isinstance(r.get('latency_ms'), (int, float)))
    return {'per_class': classes, 'confusion_matrix': matrix, 'error_breakdown': groups,
            'latency_ms': {'measured_cases': len(times), 'missing_cases': len(records) - len(times),
                           'mean': sum(times) / len(times) if times else None,
                           'min': min(times) if times else None, 'max': max(times) if times else None,
                           'total': sum(times) if times else None,
                           **{f'p{p}': times[math.ceil(p / 100 * len(times))-1] if times else None
                              for p in (50, 90, 95, 99)}},
            'latency_population': 'all completed attempts, including failures; wall time including retries; nearest-rank percentiles'}


def summary(config, report):
    def value(v):
        return 'unavailable' if v is None else str(v)
    lines = ['# Evaluation summary', '', '## Run configuration', '', '```json',
             json.dumps(config, indent=2), '```', '', '## Metrics', '',
             f"Completed {report['evaluated_cases']} / {report['selected_cases']} selected cases.", '']
    for key in ('accuracy', 'violation_recall', 'unsafe_allow_rate', 'false_block_rate', 'escalation_recall', 'invalid_responses'):
        lines.append(f'- {key}: {value(report[key])}')
    lines += ['', 'Accuracy includes invalid attempts as incorrect. Recall denominators include all completed gold cases. '
              'Unsafe allows = gold violations predicted allow / gold violations. False blocks = gold allows predicted violation or escalate / gold allows.',
              '', '## Per-class metrics', '', '| Class | Precision | Recall | F1 | Support |', '|---|---:|---:|---:|---:|']
    for label, m in report['per_class'].items():
        lines.append('| ' + ' | '.join([label] + [value(m[k]) for k in ('precision', 'recall', 'f1', 'support')]) + ' |')
    lines += ['', '## Confusion matrix (gold rows, predicted columns)', '', '| Gold | allow | violation | escalate | invalid |', '|---|---:|---:|---:|---:|']
    for label, row in report['confusion_matrix'].items():
        lines.append('| ' + ' | '.join([label] + [str(v) for v in row.values()]) + ' |')
    lines += ['', '## Latency', '', report['latency_population'], '',
              f"Measured cases: {report['latency_ms']['measured_cases']}; missing cases: {report['latency_ms']['missing_cases']}.",
              '', '| Statistic | Milliseconds |', '|---|---:|']
    for key in ('p50', 'p90', 'p95', 'p99', 'mean', 'min', 'max', 'total'):
        lines.append(f"| {key.upper()} | {value(report['latency_ms'][key])} |")
    lines += ['', 'Total is summed measured inference wall time, not full run duration or throughput. '
              'Small samples make tail percentiles unstable. Streaming time-to-first-token is not measured.',
              '', '## Token usage', '', 'Provider-reported usage from returned responses only; unreported retry usage is excluded.',
              '', '| Tokens | Measured cases | Missing cases | Total | Mean |', '|---|---:|---:|---:|---:|']
    for field, counts in report['token_usage'].items():
        lines.append('| ' + ' | '.join([field] + [value(counts[k]) for k in ('measured_cases', 'missing_cases', 'total', 'mean')]) + ' |')
    cost = report['cost_usd']
    lines += ['', '## Cost (USD)', '', cost['basis'], '',
              f"Status: {cost['status']}; priced cases: {cost['priced_cases']}; observed-usage estimate: {value(cost['observed_usage_estimate'])}; all-cases estimate: {value(cost['all_cases_estimate'])}.",
              'Local Ollama has no Ollama token fee; hardware, electricity and rented compute costs are not measured. '
              'No cloud rate is inferred automatically from a model name.',
              '', '## Error breakdown', '', 'Errors include wrong verdicts and invalid responses; grouped by gold annotation rule.', '']
    for dimension, groups in report['error_breakdown'].items():
        lines += [f'### {dimension}', '', '| Group | Cases | Errors | Invalid |', '|---|---:|---:|---:|']
        for key, counts in sorted(groups.items()):
            lines.append(f"| {key} | {counts['cases']} | {counts['errors']} | {counts['invalid']} |")
        lines.append('')
    return '\n'.join(lines) + '\n'
