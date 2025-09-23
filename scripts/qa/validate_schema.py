import json
import sys
from jsonschema import validate, Draft202012Validator
from pathlib import Path


if __name__ == "__main__":
if len(sys.argv) < 3:
print("Usage: python validate_schema.py data/tools.json data/schema/tools.schema.json")
sys.exit(2)
data_path = Path(sys.argv[1])
schema_path = Path(sys.argv[2])
data = json.loads(data_path.read_text(encoding='utf-8'))
schema = json.loads(schema_path.read_text(encoding='utf-8'))


v = Draft202012Validator(schema)
errors = sorted(v.iter_errors(data), key=lambda e: e.path)
if errors:
for e in errors[:50]:
print(f"Schema error at {'/'.join(map(str,e.path))}: {e.message}")
print(f"Total errors: {len(errors)}")
sys.exit(1)
print("Schema validation OK")
