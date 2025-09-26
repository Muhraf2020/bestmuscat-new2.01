# scripts/ingest/hydrate_details.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple, Optional
import requests
from io import BytesIO
from PIL import Image

from scripts.utils.env import GOOGLE_MAPS_API_KEY, USER_AGENT
from scripts.media.fetch_photos_google import fetch_google_photo
from scripts.utils.hours import parse_hours

TOOLS_JSON = Path("data/tools.json")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

# ---- Inline simple downloader to avoid flaky imports ----
def _download_to_webp(url: str, out_path: Path, max_width: int = 1600, quality: int = 80) -> Optional[str]:
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        r = SESSION.get(url, timeout=30)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGB")
        if img.width > max_width:
            new_h = int(img.height * (max_width / img.width))
            img = img.resize((max_width, new_h))
        img.save(out_path, format="WEBP", quality=quality, method=6)
        return str(out_path)
    except Exception:
        return None

# ---- Google Places ----
PLACES_DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"

def google_place_details(place_id: str) -> Optional[Dict[str, Any]]:
    if not GOOGLE_MAPS_API_KEY or not place_id:
        return None
    params = {
        "place_id": place_id,
        "key": GOOGLE_MAPS_API_KEY,
        "language": "en",
        "fields": (
            "name,formatted_phone_number,website,geometry,"
            "opening_hours,photos,address_components"
        ),
    }
    r = SESSION.get(PLACES_DETAILS, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK":
        return None
    return data.get("result")

# ---- Wikidata image (simple) ----
WD_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

def wikidata_main_image(qid: str) -> Optional[str]:
    if not qid:
        return None
    r = SESSION.get(WD_ENTITY.format(qid=qid), timeout=30)
    if r.status_code != 200:
        return None
    try:
        ent = next(iter(r.json().get("entities", {}).values()))
    except StopIteration:
        return None
    claims = ent.get("claims", {})
    if "P18" in claims:
        try:
            file_name = claims["P18"][0]["mainsnak"]["datavalue"]["value"]
            return f"https://commons.wikimedia.org/wiki/Special:FilePath/{file_name.replace(' ', '_')}"
        except Exception:
            return None
    return None

# ---- Helpers to read IDs from either sources{} or top-level ----
def get_source_value(place: Dict[str, Any], key: str) -> Optional[str]:
    sources = place.get("sources") or {}
    return (sources.get(key) or place.get(key)) or None

def safe_set_actions(place: Dict[str, Any], website: Optional[str], phone: Optional[str]) -> bool:
    updated = False
    if website or phone:
        actions = place.setdefault("actions", {})
        if website and not actions.get("website"):
            actions["website"] = website
            updated = True
        if phone and not actions.get("phone"):
            actions["phone"] = phone
            updated = True
        if not actions:  # if still empty, remove
            place.pop("actions", None)
    return updated

def safe_set_address_components(place: Dict[str, Any], comps: list[dict]) -> bool:
    """
    Fill top-level address (and city/country if confidently present) ONLY if missing.
    """
    updated = False
    if not comps:
        return False

    # Build a simple street address from common components
    parts = []
    for c in comps:
        types = set(c.get("types", []))
        if {"street_number"} & types or {"route"} & types or {"premise"} & types or {"subpremise"} & types:
            parts.append(c.get("long_name", ""))

    if not place.get("address") and parts:
        addr = " ".join([p for p in parts if p])
        if addr:
            place["address"] = addr
            updated = True

    if not place.get("city"):
        for c in comps:
            if "locality" in c.get("types", []) or "postal_town" in c.get("types", []):
                place["city"] = c.get("long_name")
                updated = True
                break

    if not place.get("country"):
        for c in comps:
            if "country" in c.get("types", []):
                place["country"] = c.get("long_name")
                updated = True
                break

    return updated

def safe_set_latlng(place: Dict[str, Any], geometry: Dict[str, Any]) -> bool:
    updated = False
    loc = (geometry or {}).get("location") or {}
    lat = loc.get("lat")
    lng = loc.get("lng")
    if place.get("lat") is None and isinstance(lat, (int, float)):
        place["lat"] = float(lat)
        updated = True
    if place.get("lng") is None and isinstance(lng, (int, float)):
        place["lng"] = float(lng)
        updated = True
    return updated

def safe_set_hours(place: Dict[str, Any], opening_hours: Dict[str, Any]) -> bool:
    """
    Only set place['hours'] if parsing yields at least one interval.
    Never write an empty weekly dict.
    """
    if place.get("hours") or not opening_hours:
        return False
    wt = opening_hours.get("weekday_text") or []
    if not wt:
        return False
    compact = "; ".join([str(t).replace("–", "-").replace("—", "-") for t in wt])
    try:
        hrs = parse_hours(compact)
    except Exception:
        return False
    # hrs should be a dict with 'weekly' possibly populated
    if isinstance(hrs, dict) and isinstance(hrs.get("weekly"), dict):
        if any(hrs["weekly"].get(d) for d in hrs["weekly"].keys()):
            place["hours"] = hrs
            return True
    return False

def safe_set_hero_from_google(place: Dict[str, Any], photos: list[dict]) -> bool:
    if not photos:
        return False
    imgs = place.setdefault("images", {})
    if imgs.get("hero"):
        return False
    pref = photos[0].get("photo_reference")
    if not pref:
        return False
    out = Path(f"assets/images/{place['slug']}/hero.webp")
    try:
        if fetch_google_photo(pref, out):
            imgs["hero"] = str(out)
            # also backfill top-level credits if not present
            place.setdefault("image_credit", "Google Maps")
            place.setdefault("image_source_url", None)
            return True
    except Exception:
        return False
    return False

def safe_set_hero_from_wikidata(place: Dict[str, Any], qid: Optional[str]) -> bool:
    if place.get("images", {}).get("hero"):
        return False
    url = wikidata_main_image(qid or "")
    if not url:
        return False
    out = Path(f"assets/images/{place['slug']}/hero.webp")
    if _download_to_webp(url, out, max_width=1600):
        imgs = place.setdefault("images", {})
        imgs["hero"] = str(out)
        # also backfill top-level credits if not present
        place.setdefault("image_credit", "Wikimedia Commons")
        place.setdefault("image_source_url", url)
        return True
    return False

def hydrate_one(place: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    updated = False

    # IDs from either sources{} or top-level
    place_id = get_source_value(place, "place_id")
    wikidata_id = get_source_value(place, "wikidata_id")

    # 1) Google Places hydrate
    if place_id:
        res = google_place_details(place_id)
        if res:
            # actions
            if safe_set_actions(place, res.get("website"), res.get("formatted_phone_number")):
                updated = True
            # address/city/country (top-level) if missing
            if safe_set_address_components(place, res.get("address_components") or []):
                updated = True
            # lat/lng (top-level) if missing
            if safe_set_latlng(place, res.get("geometry") or {}):
                updated = True
            # hours only if not already present AND parse yields intervals
            if safe_set_hours(place, res.get("opening_hours") or {}):
                updated = True
            # hero from Google photo if missing
            if safe_set_hero_from_google(place, res.get("photos") or []):
                updated = True

    # 2) Wikidata/Commons hero if still missing
    if safe_set_hero_from_wikidata(place, wikidata_id):
        updated = True

    return place, updated

if __name__ == "__main__":
    data = []
    if TOOLS_JSON.exists():
        data = json.loads(TOOLS_JSON.read_text(encoding="utf-8"))
    changed = 0
    new_data = []
    for place in data:
        # ensure slug/id present; skip otherwise
        if not place.get("slug") and place.get("id"):
            place["slug"] = place["id"]
        place, upd = hydrate_one(place)
        if upd:
            changed += 1
        new_data.append(place)
    TOOLS_JSON.write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Hydrate complete; updated {changed} place(s)")
