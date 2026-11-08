import unittest
import os
from unittest.mock import patch
from eval.run_eval import debug_text
from eval.reporting import diagnostics, summary, usage_and_cost, validate_pricing


class ReportingTests(unittest.TestCase):
    def test_authentication_secrets_are_masked_in_diagnostics(self):
        with patch.dict(os.environ, {'GROQ_API_KEY': 'private-key-example'}):
            self.assertEqual(debug_text('private-key-example Bearer abc123456'), '[REDACTED] Bearer [REDACTED]')

    def test_invalids_denominators_percentiles_and_error_groups(self):
        records = [dict(gold=g, pred=p, event={'kind': kind}, gold_rule=rule, latency_ms=ms)
                   for g,p,kind,rule,ms in [
                       ('violation','allow','tool_call','R2',10),
                       ('violation','violation','tool_call','R2',20),
                       ('allow','parse_error','tool_response',None,30),
                       ('escalate','escalate','user_input',None,40)]]
        result = diagnostics(records)
        self.assertEqual(result['per_class']['violation']['recall'], .5)
        self.assertEqual(result['per_class']['violation']['precision'], 1)
        self.assertEqual(result['per_class']['allow']['precision'], 0)
        self.assertEqual(result['confusion_matrix']['allow']['invalid'], 1)
        self.assertEqual(result['latency_ms'], {'measured_cases': 4, 'missing_cases': 0, 'p50': 20, 'p90': 40, 'p95': 40, 'p99': 40, 'mean': 25, 'min': 10, 'max': 40, 'total': 100})
        self.assertEqual(result['error_breakdown']['gold_policy_rule']['R2']['errors'], 1)
        self.assertEqual(result['error_breakdown']['event_kind']['tool_response']['invalid'], 1)
        self.assertIsNone(diagnostics([])['latency_ms']['p50'])
        self.assertIsNone(diagnostics([])['per_class']['allow']['precision'])

    def test_usage_cost_partial_missing_and_zero_counts(self):
        records = [{'prompt_tokens': 1000, 'completion_tokens': 500},
                   {'prompt_tokens': 0, 'completion_tokens': 0}, {}]
        result = usage_and_cost(records, 2, 4)
        self.assertEqual(result['token_usage']['prompt_tokens']['total'], 1000)
        self.assertEqual(result['token_usage']['prompt_tokens']['mean'], 500)
        self.assertEqual(result['token_usage']['completion_tokens']['missing_cases'], 1)
        self.assertAlmostEqual(result['cost_usd']['observed_usage_estimate'], .004)
        self.assertIsNone(result['cost_usd']['all_cases_estimate'])
        self.assertEqual(result['cost_usd']['priced_cases'], 2)
        self.assertAlmostEqual(usage_and_cost(records[:2], 2, 4)['cost_usd']['all_cases_estimate'], .004)
        self.assertIsNone(usage_and_cost(records)['cost_usd']['observed_usage_estimate'])
        self.assertIsNone(usage_and_cost([{}])['token_usage']['prompt_tokens']['total'])
        self.assertEqual(usage_and_cost(records[:2], 0, 0)['cost_usd']['all_cases_estimate'], 0)
        for prices in ((None, 1), (1, None), (-1, 1), (float('nan'), 1), (1, float('inf'))):
            with self.subTest(prices=prices), self.assertRaises(ValueError):
                validate_pricing(*prices)

    def test_nearest_rank_tail_percentiles_and_missing_latency(self):
        records = [dict(gold='allow', pred='allow', event={'kind': 'user_input'}, latency_ms=i)
                   for i in range(1, 101)]
        records.append(dict(gold='allow', pred='error', event={'kind': 'user_input'}))
        result = diagnostics(records)['latency_ms']
        self.assertEqual([result[k] for k in ('p50','p90','p95','p99')], [50,90,95,99])
        self.assertEqual(result['missing_cases'], 1)
        self.assertEqual(result['total'], 5050)
