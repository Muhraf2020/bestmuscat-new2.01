import json
from pathlib import Path


TOOLS_JSON = Path("data/tools.json")


REQUIRED_BY_CAT = {
"Hotel": ["actions.website","actions.phone","images.hero","location.address"],
"Restaurant": ["actions.phone","images.hero","location.address","hours"],
"Mall": ["actions.website","images.hero","location.address","hours"],
}


def get(d: dict, path: str):
cur = d
for part in path.split('.'):
if isinstance(cur, dict) and part in cur:
cur = cur[part]
else:
return None
return cur


if __name__ == "__main__":
data = json.loads(TOOLS_JSON.read_text(encoding='utf-8')) if TOOLS_JSON.exists() else []
missing = []
for p in data:
cats = p.get("categories", [])
cat = cats[0] if cats else None
req = REQUIRED_BY_CAT.get(cat, [])
for field in req:
if not get(p, field):
missing.append((p.get("slug"), field))
if missing:
print("Missing fields (friendly):")
for slug, field in missing:
print(f" - {slug}: {field}")
else:
print("All good: no category-required fields missing.")
