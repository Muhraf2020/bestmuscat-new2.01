# scripts/qa/validate_schema.py
import json
import sys
from jsonschema import Draft202012Validator
from pathlib import Path

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python validate_schema.py data/tools.json data/schema/tools.schema.json")
        sys.exit(2)

    data_path = Path(sys.argv[1])
    schema_path = Path(sys.argv[2])

    data = json.loads(data_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))

    if errors:
        for e in errors[:50]:
            where = "/".join(map(str, e.path)) or "(root)"
            print(f"Schema error at {where}: {e.message}")
        print(f"Total errors: {len(errors)}")
        sys.exit(1)

    print("Schema validation OK")
