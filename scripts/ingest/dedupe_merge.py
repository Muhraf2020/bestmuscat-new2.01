# Minimal dedupe/merge stub: pass-through normalized -> merged
from pathlib import Path
import json

src = Path('scripts/tmp/normalized.jsonl')
dst = Path('scripts/tmp/merged.jsonl')
dst.parent.mkdir(parents=True, exist_ok=True)

if not src.exists():
    dst.write_text('', encoding='utf-8')
else:
    dst.write_text(src.read_text(), encoding='utf-8')
print(f"Wrote {dst}")
