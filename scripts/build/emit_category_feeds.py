import json, os, pathlib
places = json.load(open("data/places.json"))
out_dir = pathlib.Path("data/categories"); out_dir.mkdir(parents=True, exist_ok=True)
by_cat = {}
for p in places:
    for c in p.get("categories",[]):
        by_cat.setdefault(c, []).append(p)
for c, rows in by_cat.items():
    fn = out_dir / (c.lower().replace(" ","-") + ".json")
    fn.write_text(json.dumps(rows, indent=2), encoding="utf-8")
print("Wrote category shards to data/categories/")
