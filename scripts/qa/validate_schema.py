import json, sys
from jsonschema import Draft202012Validator
from pathlib import Path

schema = json.load(open("scripts/utils/schema_place.json"))
places_path = Path("data/places.json")
if not places_path.exists():
    print("No data/places.json found."); sys.exit(1)
places = json.load(open(places_path))

errors = []
for p in places:
    for e in Draft202012Validator(schema).iter_errors(p):
        errors.append(f"[{p.get('slug')}] {e.message}")

if errors:
    print("\n".join(errors)); sys.exit(1)
print("Schema OK")
