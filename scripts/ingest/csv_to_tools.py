#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv, json, os, glob, re, sys
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse
from typing import Optional
from scripts.utils.hours import parse_hours as _parse_hours

ROOT = Path(__file__).resolve().parents[2]  # repo root
DATA_DIR = ROOT / "data"
SRC_DIR  = DATA_DIR / "sources"
TOOLS_JSON = DATA_DIR / "tools.json"
SCHEMA_FILE = DATA_DIR / "schema" / "tools.schema.json"

# ---------- Core CSV columns (keep these) ----------
CORE_HEADERS = [
    "id","slug","name","category","tagline","tags",
    "neighborhood","address","city","country","lat","lng",
    "website","phone","maps_url","hours_raw",
    "logo_url","hero_url","image_credit","image_source_url",
    "place_id","osm_type","osm_id","wikidata_id","url",
]

# ---------- Category-specific (all optional) ----------
CATEGORY_HEADERS = {
    "Hotels": [
        "price_range","busyness_hint","rating_overall",
        "sub_food_quality","sub_service","sub_ambience","sub_value","sub_accessibility",
        "review_source","review_count","review_insight","last_updated",
        "about_short","about_long","amenities"
    ],
    "Restaurants": [
        "price_range","busyness_hint","rating_overall",
        "sub_food_quality","sub_service","sub_ambience","sub_value","sub_accessibility",
        "review_source","review_count","review_insight","last_updated",
        "about_short","about_long","amenities","cuisines","meals","menu_url"
    ],
    "Schools": [
        "price_range","busyness_hint","rating_overall",
        "sub_food_quality","sub_service","sub_ambience","sub_value","sub_accessibility",
        "review_source","review_count","review_insight","last_updated",
        "about_short","about_long","amenities"
    ],
    "Malls": [
        "price_range","busyness_hint",
        "about_short","about_long","amenities"
    ],
}

# ---------- Helpers ----------
def read_json(path: Path, default):
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return default

def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def as_float(x) -> Optional[float]:
    try:
        s = str(x).strip()
        if s == "": return None
        v = float(s)
        return v if v == v else None  # NaN guard
    except Exception:
        return None

def as_int(x) -> Optional[int]:
    try:
        s = str(x).strip()
        if s == "": return None
        return int(float(s))
    except Exception:
        return None

def split_list(x):
    if x is None: return None
    s = str(x).strip()
    if not s: return None
    parts = re.split(r"[;|/,+]", s)
    parts = [p.strip() for p in parts if p.strip()]
    return parts or None

def load_csv_rows(path: Path, implied_category: Optional[str] = None):
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            r = { (k.strip() if k else k): (v.strip() if isinstance(v,str) else v) for k,v in r.items() }
            if implied_category and not r.get("category"):
                r["category"] = implied_category
            rows.append(r)
        return rows

def discover_rows():
    rows = []
    mapping = [
        ("Hotels",      SRC_DIR / "hotels.csv"),
        ("Restaurants", SRC_DIR / "restaurants.csv"),
        ("Schools",     SRC_DIR / "schools.csv"),
        ("Malls",       SRC_DIR / "malls.csv"),
    ]
    for cat, p in mapping:
        if p.exists():
            rows += load_csv_rows(p, implied_category=cat)
    # legacy catch-all (optional)
    for p in SRC_DIR.glob("*.csv"):
        if p.name.lower() in {"hotels.csv","restaurants.csv","schools.csv","malls.csv"}:
            continue
        rows += load_csv_rows(p)
    return rows

def parse_hours(hours_raw: str):
    # Use the real parser; if nothing useful parsed, return None
    if not hours_raw or not str(hours_raw).strip():
        return None
    try:
        hrs = _parse_hours(str(hours_raw).strip(), tz="Asia/Muscat")
        # If weekly has no intervals at all, drop hours (schema prefers None over empty)
        if isinstance(hrs, dict) and isinstance(hrs.get("weekly"), dict):
            if all((not v) for v in hrs["weekly"].values()):
                return None
        return hrs
    except Exception:
        return None
    # Accept JSON-ish or OSM-like "Mo-Fr 09:00-17:00; Sa-Su 10:00-22:00"
    # For now, just return a minimal structure; replace with your real parser if present.
    return {"tz":"Asia/Muscat","weekly":{}}

def download_and_localize_image(url: str, slug: str, kind: str):
    """
    If you already have an image downloader/optimizer in this repo, call it here.
    Otherwise, we just keep the URL (no download in CI).
    """
    return url  # keep remote URL unless you call your downloader

# ---------- Row -> item mapping ----------
def build_item_from_row(row: dict):
    # Core
    slug = row.get("slug")
    item = {
        "id": row.get("id") or slug,
        "slug": slug,
        "name": row.get("name"),
        "tagline": row.get("tagline") or "",
        "categories": [ (row.get("category") or "").strip() ] if row.get("category") else [],
        "tags": split_list(row.get("tags")) or [],
        "location": {
            "neighborhood": row.get("neighborhood") or None,
            "address": row.get("address") or None,
            "city": row.get("city") or None,
            "country": row.get("country") or None,
            "lat": as_float(row.get("lat")),
            "lng": as_float(row.get("lng")),
        },
        "actions": {
            "website": row.get("website") or None,
            "phone": row.get("phone") or None,
            "maps_url": row.get("maps_url") or None
        },
        "hours": parse_hours(row.get("hours_raw") or None),
        "images": {
            "logo": row.get("logo_url") or None,
            "hero": row.get("hero_url") or None,
            "credit": row.get("image_credit") or None,
            "source_url": row.get("image_source_url") or None
        },
        "sources": {
            "place_id": row.get("place_id") or None,
            "osm": {
                "type": row.get("osm_type") or None,
                "id": row.get("osm_id") or None,
            },
            "wikidata_id": row.get("wikidata_id") or None
        },
        "url": row.get("url") or None
    }

    # Category-specific / common detail fields
    cat = item["categories"][0] if item["categories"] else ""
    extras = CATEGORY_HEADERS.get(cat, [])

    price_range    = row.get("price_range") or None
    busyness_hint  = row.get("busyness_hint") or None
    rating_overall = as_float(row.get("rating_overall"))

    subscores = {
        "Food Quality":              as_float(row.get("sub_food_quality")),
        "Service":                   as_float(row.get("sub_service")),
        "Ambience":                  as_float(row.get("sub_ambience")),
        "Value for Money":           as_float(row.get("sub_value")),
        "Accessibility & Amenities": as_float(row.get("sub_accessibility")),
    }
    if all(v is None for v in subscores.values()):
        subscores = None

    public_reviews = {
        "source": row.get("review_source") or None,
        "count":  as_int(row.get("review_count")),
        "insight": row.get("review_insight") or None,
        "last_updated": row.get("last_updated") or None
    }
    if all(public_reviews.get(k) in (None, "") for k in public_reviews):
        public_reviews = None

    about = {
        "short": row.get("about_short") or None,
        "long":  row.get("about_long")  or None
    }
    if not about["short"] and not about["long"]:
        about = None

    if price_range:                item["price_range"] = price_range
    if busyness_hint:              item["busyness_hint"] = busyness_hint
    if rating_overall is not None: item["rating_overall"] = rating_overall
    if subscores:                  item["subscores"] = subscores
    if public_reviews:             item["public_reviews"] = public_reviews
    if about:                      item["about"] = about

    if "amenities" in extras:
        am = split_list(row.get("amenities"))
        if am: item["amenities"] = am
    if "cuisines" in extras:
        cu = split_list(row.get("cuisines"))
        if cu: item["cuisines"] = cu
    if "meals" in extras:
        me = split_list(row.get("meals"))
        if me: item["meals"] = me
    if "menu_url" in extras and row.get("menu_url"):
        act = item.get("actions", {}) or {}
        act["menu"] = row.get("menu_url")
        item["actions"] = act

    # Optional: image localization (call your downloader if needed)
    # item["images"]["logo"] = download_and_localize_image(item["images"]["logo"], slug, "logo") if item["images"]["logo"] else None
    # item["images"]["hero"] = download_and_localize_image(item["images"]["hero"], slug, "hero") if item["images"]["hero"] else None

    return item

def merge_items(existing: dict, new_item: dict):
    """Shallow merge by slug. New values overwrite; existing keys preserved when new is None."""
    slug = new_item.get("slug")
    old = existing.get(slug, {})
    out = dict(old)

    def merge_obj(key):
        a = old.get(key, {}) or {}
        b = new_item.get(key, {}) or {}
        m = dict(a); m.update({k:v for k,v in b.items() if v not in (None, "")})
        return m

    # top-level
    for k,v in new_item.items():
        if isinstance(v, dict):
            out[k] = merge_obj(k)
        elif v not in (None, ""):
            out[k] = v
        else:
            out.setdefault(k, v)

    existing[slug] = out
    return existing

def main():
    rows = discover_rows()
    if not rows:
        print("No CSV rows discovered under data/sources/*.csv", file=sys.stderr)
        sys.exit(0)

    for h in CORE_HEADERS:
        pass  # columns are optional; we don't hard-fail for missing now

    existing = { it["slug"]: it for it in read_json(TOOLS_JSON, []) if "slug" in it }
    merged = dict(existing)

    seen = set()
    for r in rows:
        slug = r.get("slug")
        if not slug:
            print("[WARN] Skipping row with no slug")
            continue
        if slug in seen:
            print(f"[WARN] Duplicate in CSV set: {slug}")
        seen.add(slug)

        item = build_item_from_row(r)
        merge_items(merged, item)

    output = list(merged.values())
    write_json(TOOLS_JSON, output)
    print(f"Wrote {len(output)} places → {TOOLS_JSON}")

if __name__ == "__main__":
    main()
