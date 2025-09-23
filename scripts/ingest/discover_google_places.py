# Placeholder: discovery via Google Places (Text Search / Nearby). Requires API key.
# For safety, this stub writes an empty discovered_raw.jsonl.
import json, sys, argparse, os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--category', required=True)
parser.add_argument('--lat', type=float, required=True)
parser.add_argument('--lng', type=float, required=True)
parser.add_argument('--radius', type=int, default=2000)
args = parser.parse_args()

out = Path('scripts/tmp'); out.mkdir(parents=True, exist_ok=True)
(out / 'discovered_raw.jsonl').write_text('', encoding='utf-8')
print("Wrote scripts/tmp/discovered_raw.jsonl (empty stub)")
