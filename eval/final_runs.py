"""Sequential frozen prompt comparisons using the existing evaluator."""
import importlib
import json
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from classifier import core
from eval.run_eval import evaluate

VERSIONS = ('v1', 'v2', 'v3')


def runtime_metadata():
    def command(args):
        try:
            return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL, timeout=15).strip()
        except (OSError, subprocess.SubprocessError):
            return None
    return {'python': platform.python_version(), 'platform': platform.platform(),
            'nvidia_smi': command(['nvidia-smi', '--query-gpu=name,uuid,driver_version,memory.total', '--format=csv,noheader']),
            'ollama_version': command(['ollama', '--version'])}


def run_final_suite(splits=('dev', 'test'), policy_file='policy_v1_1.md', context_size=6,
                    model='qwen3:4b', experiment_prefix='final', output_root='results',
                    warmup=True, on_result=None, hardware=None):
    splits = tuple(splits)
    if not splits or len(set(splits)) != len(splits) or any(s not in ('dev', 'test') for s in splits):
        raise ValueError('Select dev, test, or both once each')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', experiment_prefix):
        raise ValueError('Experiment prefix must contain only letters, numbers, underscores or hyphens')
    policy_path = Path(policy_file)
    if not policy_path.is_absolute():
        policy_path = core.ROOT / policy_path
    policy = policy_path.read_text(encoding='utf-8-sig')
    hardware = runtime_metadata() if hardware is None else hardware
    gpu = re.sub(r'[^A-Za-z0-9]+', '_', (hardware.get('nvidia_smi') or 'gpu_unavailable').split(',')[0]).strip('_')
    batch_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid4().hex[:8]
    batch = Path(output_root) / f'{experiment_prefix}_batch_{gpu}_{batch_id}'
    batch.mkdir(parents=True, exist_ok=False)
    manifest = {'batch_id': batch_id, 'hardware': hardware, 'policy_file': str(policy_file),
                'splits': list(splits), 'versions': list(VERSIONS), 'model': model,
                'context_size': context_size, 'warmup_per_run': warmup, 'runs': [], 'status': 'running',
                'comparison_scope': 'Historical system prompts only; current shared event rendering, schema, parser and log-only rule scoping. No historical deterministic verdict rewriting.'}
    def save():
        (batch / 'batch_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    save()
    try:
        # Complete all development runs before the held-out comparison when both are selected.
        for split in splits:
            for version in VERSIONS:
                prompt = importlib.import_module(f'classifier.prompts.prompt_{version}')
                name = f'{experiment_prefix}_{version}_{split}_{gpu}'
                entry = {'experiment': name, 'version': version, 'split': split,
                         'prompt_source_commit': prompt.SOURCE_COMMIT, 'status': 'starting', 'results_dir': None}
                manifest['runs'].append(entry)
                save()
                result = None
                try:
                    if warmup:
                        # Synthetic event only, never a dev/test target; not part of measured metrics.
                        core.classify({'kind': 'user_input', 'content': 'Hello.'}, provider='ollama', model=model,
                                      policy_text=policy, n_context=context_size, system_prompt_template=prompt.SYSTEM)
                    placement = runtime_metadata() if hardware.get('nvidia_smi') else hardware
                    try:
                        placement['ollama_ps'] = subprocess.check_output(['ollama', 'ps'], text=True, timeout=15)
                    except (OSError, subprocess.SubprocessError):
                        placement['ollama_ps'] = None
                    result = evaluate(name, policy_file=policy_file, context_size=context_size, split=split,
                                      model=model, output_root=batch, system_prompt_template=prompt.SYSTEM,
                                      experiment_metadata={'batch_id': batch_id, 'prompt_version': version,
                                                           'prompt_source_commit': prompt.SOURCE_COMMIT,
                                                           'runtime': placement, 'warmup_performed': warmup,
                                                           'latency_protocol': 'one synthetic warmup per run excluded from metrics' if warmup else 'no warmup; cold start may be included'})
                    entry.update(status='completed', results_dir=str(result))
                except BaseException as exc:
                    result = getattr(exc, 'results_dir', None)
                    entry.update(status='interrupted', results_dir=str(result) if result else None,
                                 error_type=type(exc).__name__)
                    raise
                finally:
                    save()
                    if on_result is not None and result is not None:
                        on_result(result)
        manifest['status'] = 'completed'
    except BaseException:
        manifest['status'] = 'interrupted'
        raise
    finally:
        save()
    return batch
