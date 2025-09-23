# scripts/ingest/hydrate_details.py
import json
from pathlib import Path
from typing import Any, Dict, Tuple
import requests

from scripts.utils.env import GOOGLE_MAPS_API_KEY, USER_AGENT
from scripts.media.fetch_photos_google import fetch_google_photo
from scripts.utils.hours import parse_hours

TOOLS_JSON = Path("data/tools.json")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

# ---- Google Places ----
PLACES_DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"

def google_place_details(place_id: str) -> Dict[str, Any] | None:
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

def wikidata_main_image(qid: str) -> str | None:
    if not qid:
        return None
    r = SESSION.get(WD_ENTITY.format(qid=qid), timeout=30)
    if r.status_code != 200:
        return None
    ent = list(r.json().get("entities", {}).values())[0]
    claims = ent.get("claims", {})
    if "P18" in claims:
        try:
            file_name = claims["P18"][0]["mainsnak"]["datavalue"]["value"]
            return f"https://commons.wikimedia.org/wiki/Special:FilePath/{file_name.replace(' ', '_')}"
        except Exception:
            return None
    return None

def hydrate_one(place: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    updated = False
    sources = place.get("sources", {}) or {}

    # 1) Google Places
    pid = sources.get("place_id")
    if pid:
        res = google_place_details(pid)
        if res:
            # actions: website / phone
            actions = place.setdefault("actions", {})
            if not actions.get("website") and res.get("website"):
                actions["website"] = res["website"]; updated = True
            if not actions.get("phone") and res.get("formatted_phone_number"):
                actions["phone"] = res["formatted_phone_number"]; updated = True

            # location: address & coords (only if missing)
            loc = place.setdefault("location", {})
            if not loc.get("address") and res.get("address_components"):
                parts = []
                for c in res["address_components"]:
                    if "street_number" in c["types"] or "route" in c["types"] or "premise" in c["types"]:
                        parts.append(c["long_name"])
                if parts:
                    loc["address"] = " ".join(parts); updated = True
            if (loc.get("lat") is None or loc.get("lng") is None) and res.get("geometry", {}).get("location"):
                gl = res["geometry"]["location"]
                loc["lat"] = loc.get("lat") if loc.get("lat") is not None else gl.get("lat")
                loc["lng"] = loc.get("lng") if loc.get("lng") is not None else gl.get("lng")
                updated = True

            # hours (only if not already set by CSV)
            if not place.get("hours") and res.get("opening_hours"):
                oh = res["opening_hours"]
                wt = oh.get("weekday_text", [])
                if wt:
                    compact = "; ".join([t.replace("–", "-").replace("—", "-") for t in wt])
                    try:
                        place["hours"] = parse_hours(compact)
                        updated = True
                    except Exception:
                        pass

            # hero photo (if missing)
            imgs = place.setdefault("images", {})
            if not imgs.get("hero") and res.get("photos"):
                pref = res["photos"][0].get("photo_reference")
                if pref:
                    out = Path(f"assets/images/{place['slug']}/hero.webp")
                    try:
                        if fetch_google_photo(pref, out):
                            imgs["hero"] = str(out)
                            updated = True
                    except Exception:
                        pass

    # 2) Wikidata/Commons hero if still missing
    if not place.get("images", {}).get("hero") and sources.get("wikidata_id"):
        url = wikidata_main_image(sources["wikidata_id"])
        if url:
            from scripts.media.fetch_from_url import download_to_webp
            out = Path(f"assets/images/{place['slug']}/hero.webp")
            try:
                download_to_webp(url, out, max_width=1600)
                imgs = place.setdefault("images", {})
                imgs["hero"] = str(out)
                imgs.setdefault("credit", "Wikimedia Commons")
                imgs.setdefault("source_url", url)
                updated = True
            except Exception:
                pass

    return place, updated

if __name__ == "__main__":
    data = json.loads(TOOLS_JSON.read_text(encoding="utf-8")) if TOOLS_JSON.exists() else []
    changed = 0
    new_data = []
    for place in data:
        place, upd = hydrate_one(place)
        if upd:
            changed += 1
        new_data.append(place)
    TOOLS_JSON.write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Hydrate complete; updated {changed} place(s)")
