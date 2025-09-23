import json, uuid, sys
from pathlib import Path
from scripts.utils.slugify import slugify
from scripts.utils.provenance import make_prov

src = Path('scripts/tmp/discovered_raw.jsonl')
dst = Path('scripts/tmp/normalized.jsonl')
dst.parent.mkdir(parents=True, exist_ok=True)

out = []
if src.exists() and src.read_text().strip():
    for line in src.read_text().splitlines():
        rec = json.loads(line)
        slug = slugify(rec.get("name",""), rec.get("neighborhood"))
        out.append({
            "id": str(uuid.uuid4()),
            "slug": slug,
            "name": rec.get("name","").strip(),
            "categories": rec.get("categories",[]),
            "location": {"lat": rec.get("lat"), "lng": rec.get("lng"), "address": rec.get("address",""), "neighborhood": rec.get("neighborhood")},
            "actions": {"website": rec.get("website"), "phone": rec.get("phone"), "maps_url": rec.get("maps_url")},
            "hours": rec.get("hours") or {},
            "provenance": [make_prov("discovery", rec.get("provider"), list(rec.keys()))],
            "last_updated": rec.get("collected_at")
        })
dst.write_text("\n".join(json.dumps(x) for x in out), encoding="utf-8")
print(f"Wrote {dst} with {len(out)} records.")
