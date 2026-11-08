"""Convert a list of dataset cases between .jsonl and .json without changing records.

Usage:
    python convert_dataset.py data/dataset.jsonl
    python convert_dataset.py data/dataset.json
    python convert_dataset.py data/dataset.jsonl --output my_editable.json
"""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('--output', type=Path)
args = parser.parse_args()

source = args.source
if source.suffix == '.jsonl':
    cases = [json.loads(line) for line in source.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    destination = args.output or source.with_suffix('.json')
    destination.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
elif source.suffix == '.json':
    cases = json.loads(source.read_text(encoding='utf-8-sig'))
    if not isinstance(cases, list):
        raise ValueError('JSON dataset must be a list of cases.')
    destination = args.output or source.with_suffix('.jsonl')
    destination.write_text(''.join(json.dumps(case, ensure_ascii=False) + '\n' for case in cases), encoding='utf-8')
else:
    parser.error('Source must end in .json or .jsonl')

print(f'Converted {len(cases)} cases: {source} -> {destination}')
