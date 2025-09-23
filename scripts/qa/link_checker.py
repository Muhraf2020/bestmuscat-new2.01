import json, re
places = json.load(open("data/places.json"))
url_re = re.compile(r'^https?://', re.I)
bad = []
for p in places:
    actions = p.get("actions",{})
    for k,v in actions.items():
        if v and not url_re.match(v):
            bad.append({"slug": p.get("slug"), "field": k, "value": v})
print(json.dumps(bad, indent=2))
