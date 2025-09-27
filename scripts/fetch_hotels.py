#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv, os, time, math, urllib.parse, requests, sys, re, json
from pathlib import Path

API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not API_KEY:
    print("ERROR: Set GOOGLE_MAPS_API_KEY in your environment.", file=sys.stderr)
    sys.exit(1)

# Center on Muscat
CENTER_LAT, CENTER_LNG = 23.5880, 58.3829

# Project paths (adjust if your tree differs)
ROOT = Path(__file__).resolve().parents[1]   # scripts/ under repo root
SRC_DIR = ROOT / "data" / "sources"
SRC_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = SRC_DIR / "hotels.csv"

ASSETS_DIR = ROOT / "assets" / "hotels"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"(^-|-$)", "", s)
    return s

def maps_place_url(place_id: str) -> str:
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"

def price_level_to_symbols(level):
    mapping = {0:"$", 1:"$", 2:"$$", 3:"$$$", 4:"$$$$"}
    return mapping.get(level, "")

def places_text_search(page_token=None):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": "hotel",
        "type": "lodging",
        "location": f"{CENTER_LAT},{CENTER_LNG}",
        "radius": 30000,
        "key": API_KEY,
    }
    if page_token:
        params = {"pagetoken": page_token, "key": API_KEY}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def place_details(place_id: str):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = [
        "place_id","name","formatted_address","geometry/location",
        "international_phone_number","website","url","business_status",
        "current_opening_hours","editorial_summary","rating","user_ratings_total",
        "price_level","photos"
        # NOTE: We skip "reviews" text to stay TOS-friendly for static storage
    ]
    params = {
        "place_id": place_id,
        "fields": ",".join(fields),
        "key": API_KEY,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def choose_best_photo(photos):
    """
    Prefer a landscape image (width >= height), else fallback to first.
    Google returns an array with width/height; we pick a good candidate.
    """
    if not photos:
        return None
    # landscape first
    landscapes = [p for p in photos if (p.get("width",0) >= p.get("height",0))]
    pick = (landscapes[0] if landscapes else photos[0])
    return pick.get("photo_reference")

def download_photo(photo_ref: str, out_path: Path, maxwidth=1600):
    """
    Download the image from the Google Photos endpoint so your site
    serves a local file (no API key exposure on the frontend).
    """
    if not photo_ref:
        return False
    base = "https://maps.googleapis.com/maps/api/place/photo"
    qs = {
        "photoreference": photo_ref,
        "maxwidth": str(maxwidth),
        "key": API_KEY
    }
    # allow redirects to final CDN image
    resp = requests.get(base, params=qs, timeout=60, allow_redirects=True)
    if resp.status_code == 200 and resp.content:
        out_path.write_bytes(resp.content)
        return True
    return False

CSV_HEADERS = [
    "id","slug","name","category","tagline","tags",
    "neighborhood","address","city","country","lat","lng",
    "website","phone","maps_url","hours_raw",
    "logo_url","hero_url","image_credit","image_source_url",
    "place_id","osm_type","osm_id","wikidata_id","url",
    "description","price_range","about_short","about_long","amenities",
    "rating_overall","sub_service","sub_ambience","sub_value","sub_accessibility",
    "review_count","review_source","review_insight","last_updated",
    # hotel-specific (kept for future enrichment)
    "star_rating","checkin_time","checkout_time","room_types","hotel_amenities",
    "booking_url","distance_to_airport","breakfast_included","parking"
]

def normalize_row(d): return {k: d.get(k, "") for k in CSV_HEADERS}

def main():
    print("Fetching Muscat hotels…")
    rows, seen = [], set()
    token, loops = None, 0

    while True:
        loops += 1
        data = places_text_search(page_token=token)
        status = data.get("status")
        if status not in ("OK","ZERO_RESULTS"):
            print("TextSearch status:", status, data.get("error_message",""), file=sys.stderr)
            break

        for it in data.get("results", []):
            pid = it.get("place_id")
            if not pid or pid in seen:
                continue
            seen.add(pid)

            time.sleep(0.2)
            det = place_details(pid)
            if det.get("status") != "OK":
                continue
            p = det.get("result", {})

            name = p.get("name","").strip()
            if not name: 
                continue
            slug = slugify(name)

            addr = p.get("formatted_address","").strip()
            loc  = (p.get("geometry") or {}).get("location") or {}
            lat  = loc.get("lat")
            lng  = loc.get("lng")

            phone  = (p.get("international_phone_number") or "").strip()
            web    = (p.get("website") or "").strip()
            rating = p.get("rating")
            ratings_total = p.get("user_ratings_total") or ""
            price_range = price_level_to_symbols(p.get("price_level"))

            # Hero: pick best photo and download locally
            hero_local = ""
            photo_ref = choose_best_photo(p.get("photos") or [])
            if photo_ref:
                out_path = ASSETS_DIR / f"{slug}.jpg"
                ok = download_photo(photo_ref, out_path, maxwidth=1600)
                if ok:
                    hero_local = str(out_path.relative_to(ROOT)).replace("\\","/")

            # Hours → store JSON raw for your parser
            hours_raw = ""
            if p.get("current_opening_hours"):
                try:
                    hours_raw = json.dumps(p["current_opening_hours"], ensure_ascii=False)
                except Exception:
                    hours_raw = ""

            editorial = (p.get("editorial_summary") or {}).get("overview","").strip()

            row = {
                "id": p.get("place_id",""),
                "slug": slug,
                "name": name,
                "category": "Hotels",
                "tagline": editorial[:140] if editorial else "",
                "tags": "hotel;lodging",
                "neighborhood": "",
                "address": addr,
                "city": "Muscat",
                "country": "Oman",
                "lat": f"{lat:.6f}" if isinstance(lat,(int,float)) else "",
                "lng": f"{lng:.6f}" if isinstance(lng,(int,float)) else "",
                "website": web,
                "phone": phone,
                "maps_url": maps_place_url(p.get("place_id","")),
                "osm_type": "",                                     # never carry OSM into CSV
                "osm_id": "",
                "hours_raw": hours_raw,
                "logo_url": "",
                "hero_url": hero_local,                     # LOCAL file (no key leak)
                "image_credit": "Image © Google",
                "image_source_url": maps_place_url(p.get("place_id","")),
                "place_id": p.get("place_id",""),
                "osm_type": "",
                "osm_id": "",
                "wikidata_id": "",
                "url": web,
                "description": editorial or "",
                "price_range": price_range,
                "about_short": "",
                "about_long": "",
                "amenities": "",                            # can enrich later
                "rating_overall": f"{rating:.2f}" if isinstance(rating,(int,float)) else "",
                "sub_service": "",
                "sub_ambience": "",
                "sub_value": "",
                "sub_accessibility": "",
                "review_count": ratings_total,              # <- GOOGLE total reviews
                "review_source": "Google",
                "review_insight": "",                      # keep blank or your own short note
                "last_updated": time.strftime("%Y-%m-%d"),
                # hotel-specific (blank for now)
                "star_rating": "",
                "checkin_time": "",
                "checkout_time": "",
                "room_types": "",
                "hotel_amenities": "",
                "booking_url": web,
                "distance_to_airport": "",
                "breakfast_included": "",
                "parking": "",
            }
            rows.append(normalize_row(row))

        token = data.get("next_page_token")
        if not token: break
        time.sleep(2.0)
        if loops > 6: break

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} hotels → {OUT_CSV}")
    print(f"Images saved to: {ASSETS_DIR}")

if __name__ == "__main__":
    main()
