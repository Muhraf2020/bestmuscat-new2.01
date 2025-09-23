# Simple search index builder (basic subset for Fuse-like fields)
import json, hashlib
places = json.load(open("data/places.json"))
index = []
for p in places:
    index.append({
        "slug": p["slug"],
        "name": p["name"],
        "categories": p.get("categories", []),
        "neighborhood": (p.get("location") or {}).get("neighborhood"),
        "badges": p.get("badges", []),
        "cuisines": p.get("cuisines", []),
        "rating": p.get("rating_overall", 0)
    })
open("data/search-index.json","w").write(json.dumps(index, indent=2))
print("Wrote data/search-index.json")
