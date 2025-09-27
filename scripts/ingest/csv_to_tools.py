#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv, json, os, glob
from pathlib import Path
from typing import Optional, Dict, Any, List
from collections import OrderedDict

# import the real hours parser and sanitize empties
from scripts.utils.hours import parse_hours as _parse_hours

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SRC_DIR  = DATA_DIR / "sources"
TOOLS_JSON = DATA_DIR / "tools.json"

# Map CSV filename stems to canonical category names
CATEGORY_FROM_FILENAME = {
    "clinics": "Clinics",
    "spas": "Spas",
    "hotels": "Hotels",
    "restaurants": "Restaurants",
    "schools": "Schools",
    "malls": "Malls",
    "places": "Places",
    # NEW:
    "garages": "Car Repair Garages",
    "home_maintenance": "Home Maintenance and Repair",
    "catering": "Catering Services",
    "events": "Event Planning and Decorations",
    "moving": "Moving and Storage",
}
# Canonical display labels for categories (normalize variants)
CATEGORY_ALIASES = {
    "events": "Events",
    "event planning and decorations": "Events",
    # add more synonyms if needed
}

REQUIRED = [
    "id","slug","name","category","tagline","tags",
    "neighborhood","address","city","country","lat","lng",
    "website","phone","maps_url","hours_raw",
    "logo_url","hero_url","image_credit","image_source_url",
    "place_id","osm_type","osm_id","wikidata_id","url",
]

def parse_hours_safe(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw or not str(raw).strip():
        return None
    try:
        hrs = _parse_hours(str(raw).strip(), tz="Asia/Muscat")
        if isinstance(hrs, dict) and isinstance(hrs.get("weekly"), dict):
            # if weekly exists but has no intervals at all, drop hours
            if not any(hrs["weekly"].get(d) for d in hrs["weekly"].keys()):
                return None
        return hrs
    except Exception:
        return None

def split_tags(s: str) -> List[str]:
    if not s: return []
    parts = [p.strip() for p in str(s).replace("；",";").split(";")]
    return [p for p in parts if p]

def read_all_csvs() -> List[Dict[str,str]]:
    # read ALL CSVs under data/sources/
    paths = sorted(SRC_DIR.glob("*.csv"))
    rows: List[Dict[str,str]] = []
    for p in paths:
        if p.stat().st_size == 0:
            continue
        stem = p.stem.lower()  # e.g., "clinics", "spas"
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                rec = {k: (v or "").strip() for k, v in r.items()}
                # If category is empty, derive from filename
                if not rec.get("category"):
                    rec["category"] = CATEGORY_FROM_FILENAME.get(stem, rec.get("category", ""))
                rows.append(rec)
    return rows

def row_to_item(r: Dict[str, str]) -> Dict[str, Any]:
    # ensure required keys exist
    for k in REQUIRED:
        r.setdefault(k, "")
   # Normalize category via aliases → canonical "Events" etc.
    cat = (r.get("category") or "").strip()
    if cat:
        key = cat.strip().lower()
        cat = CATEGORY_ALIASES.get(key, cat.strip())
    # else: empty will already have been set from filename in read_all_csvs()
    cats = [cat] if cat else []


    item = OrderedDict({
        "id": r["id"].strip() or (r.get("slug") or ""),
        "slug": (r["slug"] or r["id"]).strip().lower().replace(" ","-"),
        "name": r["name"].strip(),
        "categories": cats,
        "tagline": r["tagline"].strip() or None,
        "tags": split_tags(r.get("tags","")),
        "neighborhood": r["neighborhood"].strip() or None,
        "address": r["address"].strip() or None,
        "city": r["city"].strip() or None,
        "country": r["country"].strip() or None,
        "lat": float(r["lat"]) if r["lat"] else None,
        "lng": float(r["lng"]) if r["lng"] else None,
        "actions": {k:v for k,v in {
            "website": r["website"].strip() or None,
            "phone": r["phone"].strip() or None,
            "maps_url": r["maps_url"].strip() or None,
        }.items() if v},
        "hours": parse_hours_safe(r.get("hours_raw")),
        "logo_url": r["logo_url"].strip() or None,
        "hero_url": r["hero_url"].strip() or None,
        "image_credit": r["image_credit"].strip() or None,
        "image_source_url": r["image_source_url"].strip() or None,
        "place_id": r["place_id"].strip() or None,
        "osm_type": r["osm_type"].strip() or None,
        "osm_id": r["osm_id"].strip() or None,
        "wikidata_id": r["wikidata_id"].strip() or None,
        "url": r["url"].strip() or None,
    })
    # Record source CSV schema & data presence for this row
    item["schema_keys"]  = list(r.keys())
    item["present_keys"] = [k for k, v in r.items() if (v or "").strip()]

    # ── BEGIN: Extend mapping for richer fields (description, pricing, ratings, amenities, etc.) ──
    # Simple string fields (trimmed; keep None if empty)
    item["description"]   = (r.get("description")   or "").strip() or None
    item["pricing"]       = (r.get("pricing")       or "").strip() or None
    item["price_range"]   = (r.get("price_range")   or "").strip() or None
    item["busyness_hint"] = (r.get("busyness_hint") or "").strip() or None
    item["last_updated"]  = (r.get("last_updated")  or "").strip() or None

    # Arrays from semicolon-separated CSV cells (reuses your split_tags helper)
    am = split_tags(r.get("amenities", ""))
    cu = split_tags(r.get("cuisines",  ""))
    me = split_tags(r.get("meals",     ""))
    if am: item["amenities"] = am
    if cu: item["cuisines"]  = cu
    if me: item["meals"]     = me

    # Ratings
    rating_overall = None
    try:
        if r.get("rating_overall"):
            rating_overall = float(r["rating_overall"])
    except ValueError:
        rating_overall = None
    if rating_overall is not None:
        item["rating_overall"] = rating_overall

    # Subscores → pack into an object only if at least one present
    subscores = OrderedDict()
    def _f(x):  # safe float
        try:
            return float(x) if x not in (None, "") else None
        except ValueError:
            return None
    subscores["Food Quality"]            = _f(r.get("sub_food_quality"))
    subscores["Service"]                 = _f(r.get("sub_service"))
    subscores["Ambience"]                = _f(r.get("sub_ambience"))
    subscores["Value for Money"]         = _f(r.get("sub_value"))
    subscores["Accessibility & Amenities"] = _f(r.get("sub_accessibility"))
    # drop keys that are None
    subscores = {k:v for k,v in subscores.items() if v is not None}
    if subscores:
        item["subscores"] = subscores

    # Public review/sentiment (count, source, summary, last_updated)
    ps = OrderedDict()
    try:
        if r.get("review_count"):
            ps["count"] = int(r["review_count"])
    except ValueError:
        pass
    source  = (r.get("review_source")  or "").strip() or None
    summary = (r.get("review_insight") or "").strip() or None
    lu2     = (r.get("last_updated")   or "").strip() or None  # reuse if filled
    if source:  ps["source"]  = source
    if summary: ps["summary"] = summary
    if lu2:     ps["last_updated"] = lu2
    if ps:
        item["public_sentiment"] = ps

    # About (short/long) – useful for enhanced detail renderer
    about_short = (r.get("about_short") or "").strip() or None
    about_long  = (r.get("about_long")  or "").strip() or None
    if about_short or about_long:
        item["about"] = {"short": about_short, "long": about_long}

    # Clean up: remove empty strings in any nested dicts we just created
    # (You already avoid empty strings above, so this is mostly belt-and-braces.)
    for k in ("about", "public_sentiment"):
        if k in item and isinstance(item[k], dict):
            for kk in list(item[k].keys()):
                if item[k][kk] in ("", None):
                    item[k].pop(kk, None)
            if not item[k]:
                item.pop(k, None)
    # ── END: Extend mapping ──

    if not item["actions"]:
        item.pop("actions", None)
    return item

def build():
    rows = read_all_csvs()
    # merge by slug: last write wins
    merged: Dict[str, Dict[str, Any]] = OrderedDict()
    for r in rows:
        slug = (r.get("slug") or r.get("id") or "").strip()
        if not slug:
            continue
        item = row_to_item(r)
        merged[slug] = item

    out = list(merged.values())
    TOOLS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with TOOLS_JSON.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(out)} items → {TOOLS_JSON}")

if __name__ == "__main__":
    build()
