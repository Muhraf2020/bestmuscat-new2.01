# scripts/ingest/csv_to_tools.py
import csv
import json
from pathlib import Path
from typing import Dict, Any

# --- inline downloader (avoids import issues) ---
import requests
from PIL import Image
from io import BytesIO

def download_to_webp(url: str, out_path: Path, max_width: int = 1600, quality: int = 80):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, timeout=30, headers={"User-Agent": "BestMuscatBot/1.0"})
    r.raise_for_status()
    img = Image.open(BytesIO(r.content)).convert("RGB")
    if img.width > max_width:
        new_height = int(img.height * (max_width / img.width))
        img = img.resize((max_width, new_height))
    img.save(out_path, format="WEBP", quality=quality, method=6)
    return str(out_path)
# -----------------------------------------------

from scripts.utils.hours import parse_hours

CSV_PATH = Path("data/sources/places.csv")
TOOLS_JSON = Path("data/tools.json")
ASSETS = Path("assets/images")

REQUIRED_COLS = [
    "id", "slug", "name", "category", "tagline", "tags",
    "neighborhood", "address", "city", "country", "lat", "lng",
    "website", "phone", "maps_url", "hours_raw", "logo_url", "hero_url",
    "image_credit", "image_source_url", "place_id", "osm_type", "osm_id",
    "wikidata_id", "url"
]

def read_csv() -> list[dict[str, str]]:
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("CSV has no rows.")
    missing = [c for c in REQUIRED_COLS if c not in rows[0].keys()]
    if missing:
        raise SystemExit(f"CSV missing columns: {missing}")
    return rows

def load_tools() -> Dict[str, Any]:
    if TOOLS_JSON.exists():
        return {x["slug"]: x for x in json.loads(TOOLS_JSON.read_text(encoding="utf-8"))}
    return {}

def save_tools(obj: Dict[str, Any]):
    arr = [obj[k] for k in sorted(obj.keys())]
    TOOLS_JSON.parent.mkdir(parents=True, exist_ok=True)
    TOOLS_JSON.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding="utf-8")

def to_float(val: str | None):
    try:
        return float(val) if val not in (None, "",) else None
    except Exception:
        return None

def split_tags(val: str | None):
    if not val:
        return []
    return [t.strip() for t in val.split(";") if t.strip()]

def ensure_slug_uniqueness(rows: list[dict]):
    seen = set()
    dups = []
    for r in rows:
        s = (r.get("slug") or "").strip()
        if s in seen:
            dups.append(s)
        seen.add(s)
    if dups:
        raise SystemExit(f"Duplicate slugs in CSV: {dups}")

def map_row(r: dict[str, str]) -> Dict[str, Any]:
    slug = (r["slug"] or "").strip()
    img_dir = ASSETS / slug
    logo_rel = f"assets/images/{slug}/logo.webp"
    hero_rel = f"assets/images/{slug}/hero.webp"

    out: Dict[str, Any] = {
        "id": (r["id"] or "").strip(),
        "slug": slug,
        "name": (r["name"] or "").strip(),
        "tagline": r.get("tagline") or "",
        "categories": [r.get("category", "")] if r.get("category") else [],
        "tags": split_tags(r.get("tags")),
        "actions": {
            "website": r.get("website") or None,
            "phone": r.get("phone") or None,
            "maps_url": r.get("maps_url") or None,
        },
        "location": {
            "neighborhood": r.get("neighborhood") or None,
            "address": r.get("address") or None,
            "city": r.get("city") or None,
            "country": r.get("country") or None,
            "lat": to_float(r.get("lat")),
            "lng": to_float(r.get("lng")),
        },
        "hours": parse_hours(r.get("hours_raw", "")) if r.get("hours_raw") else None,
        "images": {
            "logo": logo_rel if (img_dir / "logo.webp").exists() else None,
            "hero": hero_rel if (img_dir / "hero.webp").exists() else None,
            "credit": r.get("image_credit") or None,
            "source_url": r.get("image_source_url") or None,
        },
        "sources": {
            "place_id": r.get("place_id") or None,
            "osm": {"type": r.get("osm_type") or None, "id": r.get("osm_id") or None},
            "wikidata_id": r.get("wikidata_id") or None,
        },
        "url": r.get("url") or None,
    }

    # Download images if URLs provided
    logo_url = r.get("logo_url")
    if logo_url:
        try:
            p = img_dir / "logo.webp"
            download_to_webp(logo_url, p, max_width=512)
            out["images"]["logo"] = f"assets/images/{slug}/logo.webp"
        except Exception:
            pass

    hero_url = r.get("hero_url")
    if hero_url:
        try:
            p = img_dir / "hero.webp"
            download_to_webp(hero_url, p, max_width=1600)
            out["images"]["hero"] = f"assets/images/{slug}/hero.webp"
        except Exception:
            pass

    return out

def merge(existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    ex = existing.copy()
    ex.update({k: v for k, v in new.items() if k in {
        "id", "slug", "name", "tagline", "categories", "tags",
        "actions", "location", "hours", "images", "sources", "url"
    }})
    for k in ("actions", "location", "images", "sources"):
        ex[k] = {**existing.get(k, {}), **new.get(k, {})}
    return ex

if __name__ == "__main__":
    rows = read_csv()
    ensure_slug_uniqueness(rows)
    tools = load_tools()

    for r in rows:
        mapped = map_row(r)
        slug = mapped["slug"]
        if slug in tools:
            tools[slug] = merge(tools[slug], mapped)
        else:
            tools[slug] = mapped

    save_tools(tools)
    print(f"Wrote {TOOLS_JSON}")
