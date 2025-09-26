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

def row_to_item(r: Dict[str, str]) -> Dict[str, Any]:
    # ensure missing keys exist
    for k in REQUIRED:
        r.setdefault(k, "")
    cats = [r["category"]] if r.get("category") else []
    item = OrderedDict({
        "id": r["id"].strip(),
        "slug": r["slug"].strip(),
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
    # drop empty actions if none
    if not item["actions"]:
        item.pop("actions", None)
    return item

def read_all_csvs() -> List[Dict[str,str]]:
    # read ALL CSVs under data/sources/
    paths = sorted(SRC_DIR.glob("*.csv"))
    rows: List[Dict[str,str]] = []
    for p in paths:
        if p.stat().st_size == 0:
            continue
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                rows.append({k:(v or "").strip() for k,v in r.items()})
    return rows

def build():
    rows = read_all_csvs()
    # merge by slug: last write wins (simple & deterministic)
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
