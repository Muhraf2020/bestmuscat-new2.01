import json, sys
from pathlib import Path

required_by_category = {
    "Restaurants": ["cuisines", "price_range", "hours"]
}

places = json.load(open("data/places.json"))
rows = []
for p in places:
    cats = p.get("categories",[])
    miss = set()
    for c in cats:
        for f in required_by_category.get(c, []):
            if not p.get(f):
                miss.add(f)
    if miss:
        rows.append({"slug": p.get("slug"), "missing": sorted(miss)})
print(json.dumps(rows, indent=2))
