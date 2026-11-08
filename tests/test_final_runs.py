import ast
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from classifier import core
from classifier.prompts import SYSTEM
from eval.final_runs import run_final_suite


class FinalRunTests(unittest.TestCase):
    def test_prompt_templates_exactly_match_history_and_v3_production(self):
        import importlib
        event = {'kind': 'user_input', 'content': 'Hello.'}
        for v, rev in [('v1','a2722bf'),('v2','64f27df'),('v3','0901c79')]:
            source = subprocess.check_output(['git','show',f'{rev}:classifier/core.py'], text=True)
            node = next(n for n in ast.parse(source).body if isinstance(n,ast.Assign)
                        and any(getattr(t,'id',None)=='SYSTEM' for t in n.targets))
            module = importlib.import_module(f'classifier.prompts.prompt_{v}')
            self.assertEqual(module.SYSTEM, ast.literal_eval(node.value))
            request = core.build_ollama_request(event, 'POLICY SENTINEL', system_prompt_template=module.SYSTEM)
            self.assertEqual(request['messages'][0]['content'], module.SYSTEM.format(policy='POLICY SENTINEL'))
            self.assertEqual(request['messages'][0]['content'].count('POLICY SENTINEL'), 1)
        from classifier.prompts.prompt_v3 import SYSTEM as V3
        self.assertEqual(V3, SYSTEM)
        self.assertEqual(core.build_ollama_request(event, 'policy'),
                         core.build_ollama_request(event, 'policy', system_prompt_template=V3))

    def test_six_runs_are_sequential_unique_and_use_frozen_templates(self):
        with tempfile.TemporaryDirectory() as directory, patch('eval.final_runs.evaluate') as evaluate, \
                patch('eval.final_runs.subprocess.check_output', return_value='GPU placement'), \
                patch.object(core, 'classify') as classify:
            evaluate.side_effect = [Path(directory)/str(i) for i in range(6)]
            callback = unittest.mock.Mock()
            batch = run_final_suite(output_root=directory, hardware={'nvidia_smi': 'Tesla T4, uuid, driver, 15360'},
                                    on_result=callback)
            calls = evaluate.call_args_list
            self.assertEqual([c.kwargs['split'] for c in calls], ['dev']*3+['test']*3)
            self.assertEqual(len({c.args[0] for c in calls}), 6)
            self.assertEqual(classify.call_count, 6)
            self.assertEqual(callback.call_count, 6)
            manifest = json.loads((batch/'batch_manifest.json').read_text())
            self.assertEqual(manifest['status'], 'completed')
            self.assertEqual([r['version'] for r in manifest['runs']], ['v1','v2','v3']*2)
            for c in calls:
                self.assertIn('Tesla_T4', c.args[0])
                self.assertEqual(c.kwargs['policy_file'], 'policy_v1_1.md')
                self.assertIn('{policy}', c.kwargs['system_prompt_template'])

    def test_fatal_error_preserves_manifest_and_reports_partial_results(self):
        with tempfile.TemporaryDirectory() as directory, patch('eval.final_runs.evaluate') as evaluate:
            error = TypeError('offline fixture'); error.results_dir = Path(directory)/'partial'
            evaluate.side_effect = error
            callback = unittest.mock.Mock()
            with self.assertRaises(TypeError):
                run_final_suite(output_root=directory, warmup=False, hardware={}, on_result=callback)
            manifest = json.loads(next(Path(directory).glob('*/batch_manifest.json')).read_text())
            self.assertEqual(manifest['status'], 'interrupted')
            self.assertEqual(len(manifest['runs']), 1)
            callback.assert_called_once_with(error.results_dir)

    def test_versioned_templates_reach_model_and_saved_snapshot_unchanged(self):
        import contextlib
        import importlib
        import io
        import httpx
        from eval.run_eval import evaluate
        case = {'id': 'fixture', 'split': 'test', 'original_request': 'Say hello',
                'agent_instructions': None, 'steps': [{'kind': 'user_input', 'content': 'Hello'}],
                'target_index': 0, 'label': 'allow', 'rule_id': None}
        answer = {'verdict': 'allow', 'evidence': None, 'rationale': 'Greeting.',
                  'rules': [], 'primary_rule': None, 'missing_fact': None}
        payloads = []
        def respond(request):
            if request.method == 'GET':
                return httpx.Response(200, json={'models': []})
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps(answer)},
                                            'prompt_eval_count': 100, 'eval_count': 20})
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'MOCK': '0'}), \
                patch('eval.run_eval.load_dataset', return_value=[case]), \
                httpx.Client(transport=httpx.MockTransport(respond)) as client, contextlib.redirect_stdout(io.StringIO()):
            for v in ('v1', 'v2', 'v3'):
                module = importlib.import_module(f'classifier.prompts.prompt_{v}')
                output = evaluate('fixture_'+v, split='test', output_root=directory, client=client,
                                  system_prompt_template=module.SYSTEM,
                                  experiment_metadata={'prompt_version': v, 'gpu': 'offline fixture'})
                policy = (output/'policy.md').read_text(encoding='utf-8')
                self.assertEqual((output/'prompt.txt').read_text(encoding='utf-8'), module.SYSTEM.format(policy=policy))
                self.assertEqual(payloads[-1]['messages'][0]['content'], module.SYSTEM.format(policy=policy))
                config = json.loads((output/'run_config.json').read_text())
                self.assertEqual(config['prompt_mode'], 'versioned_template')
                self.assertEqual(config['experiment_metadata']['prompt_version'], v)
                self.assertEqual(config['split'], 'test')
                self.assertEqual(json.loads((output/'metrics.json').read_text())['token_usage']['prompt_tokens']['total'], 100)
