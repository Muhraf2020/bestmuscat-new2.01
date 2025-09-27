#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv, os, time, math, urllib.parse, requests, sys, re, json, argparse
from pathlib import Path
import mimetypes
from time import sleep

API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not API_KEY:
    print("ERROR: Set GOOGLE_MAPS_API_KEY in your environment.", file=sys.stderr)
    sys.exit(1)

# Center on Muscat (kept for default single-query compatibility)
CENTER_LAT, CENTER_LNG = 23.5880, 58.3829

# Project paths (adjust if your tree differs)
ROOT = Path(__file__).resolve().parents[1]   # scripts/ under repo root
SRC_DIR = ROOT / "data" / "sources"
SRC_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = SRC_DIR / "hotels.csv"

ASSETS_DIR = ROOT / "assets" / "hotels"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# ---------- Utilities ----------
def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"(^-|-$)", "", s)
    return s

def maps_place_url(place_id: str) -> str:
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"

def is_maps_fallback(url: str) -> bool:
    return (url or "").startswith("https://www.google.com/maps/place/?q=place_id:")

def price_level_to_symbols(level):
    mapping = {0:"$", 1:"$", 2:"$$", 3:"$$$", 4:"$$$$"}
    return mapping.get(level, "")

# --- helper: robust GET with simple retries ---
def http_get(url, params=None, timeout=30, allow_redirects=True, max_retries=3, backoff=1.5):
    attempt = 0
    while True:
        try:
            r = requests.get(url, params=params, timeout=timeout, allow_redirects=allow_redirects)
            r.raise_for_status()
            return r
        except Exception:
            attempt += 1
            if attempt >= max_retries:
                raise
            time.sleep(backoff ** attempt)

# ---------- Google Places wrappers ----------
def places_text_search(keyword: str, lat: float, lng: float, radius_m: int, page_token=None):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    # For initial call, use full params; for page_token calls, only key/pagetoken
    if page_token:
        params = {"pagetoken": page_token, "key": API_KEY}
    else:
        params = {
            "query": keyword,
            "type": "lodging",  # keep type to bias results
            "location": f"{lat},{lng}",
            "radius": radius_m,
            "key": API_KEY,
        }
    r = http_get(url, params=params, timeout=30)
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
    r = http_get(url, params=params, timeout=30)
    return r.json()

def choose_best_photo(photos):
    """
    Prefer a landscape image (width >= height), else fallback to first.
    """
    if not photos:
        return None
    landscapes = [p for p in photos if (p.get("width",0) >= p.get("height",0))]
    pick = (landscapes[0] if landscapes else photos[0])
    return pick.get("photo_reference")

def download_photo(photo_ref: str, out_path: Path, maxwidth=1600):
    """
    Downloads the image; returns the final path (with inferred extension) or False.
    """
    if not photo_ref:
        return False
    base = "https://maps.googleapis.com/maps/api/place/photo"
    qs = {"photoreference": photo_ref, "maxwidth": str(maxwidth), "key": API_KEY}
    resp = http_get(base, params=qs, timeout=60, allow_redirects=True, max_retries=3)
    if resp.status_code == 200 and resp.content:
        ct = resp.headers.get("Content-Type", "")
        ext = mimetypes.guess_extension(ct) or ".jpg"
        out_path = out_path.with_suffix(ext)
        out_path.write_bytes(resp.content)
        return out_path
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

def normalize_row(d): 
    return {k: d.get(k, "") for k in CSV_HEADERS}

# Merge strategy: fill blanks, prefer official website over maps fallback, keep any better hero
def merge_rows(old, new):
    merged = dict(old)
    for k, v in new.items():
        ov = merged.get(k, "")
        if k == "website":
            # Prefer non-Maps URL over maps fallback
            if (not ov) or is_maps_fallback(ov):
                if v:
                    merged[k] = v
        elif k == "hero_url":
            # Prefer existing if already set; otherwise take new
            if not ov and v:
                merged[k] = v
        elif k in ("rating_overall","review_count"):
            # keep the one that is non-empty and (for reviews) larger if both present
            if k == "review_count":
                try:
                    oi = int(ov) if str(ov).strip().isdigit() else -1
                    ni = int(v) if str(v).strip().isdigit() else -1
                    if ni > oi:
                        merged[k] = v
                except Exception:
                    if not ov and v:
                        merged[k] = v
            else:
                if not ov and v:
                    merged[k] = v
        else:
            if not ov and v:
                merged[k] = v
    return merged

def build_row(text_item: dict, details: dict):
    p = details
    name = p.get("name","").strip()
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

    # Photos: prefer Details photos, else fall back to TextSearch photos
    details_photos = p.get("photos") or []
    seed_photos = text_item.get("photos") or []
    chosen_ref = choose_best_photo(details_photos) or choose_best_photo(seed_photos)

    hero_local = ""
    if chosen_ref:
        out_path = ASSETS_DIR / f"{slug}"
        saved = download_photo(chosen_ref, out_path, maxwidth=1600)
        if saved:
            hero_local = str(saved.relative_to(ROOT)).replace("\\","/")

    # Hours → store JSON raw
    hours_raw = ""
    if p.get("current_opening_hours"):
        try:
            hours_raw = json.dumps(p["current_opening_hours"], ensure_ascii=False)
        except Exception:
            hours_raw = ""

    editorial = (p.get("editorial_summary") or {}).get("overview","").strip()

    # Website fallback to Maps URL if missing
    maps_url = maps_place_url(p.get("place_id",""))
    if not web:
        web = maps_url

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
        "website": web,                       # fallback ensures non-empty
        "phone": phone,
        "maps_url": maps_url,
        "hours_raw": hours_raw,
        "logo_url": "",
        "hero_url": hero_local,               # LOCAL file (no key leak)
        "image_credit": "Image © Google",
        "image_source_url": maps_url,
        "place_id": p.get("place_id",""),
        "osm_type": "",
        "osm_id": "",
        "wikidata_id": "",
        "url": web,
        "description": editorial or "",
        "price_range": price_range,
        "about_short": "",
        "about_long": "",
        "amenities": "",
        "rating_overall": f"{rating:.2f}" if isinstance(rating,(int,float)) else "",
        "sub_service": "",
        "sub_ambience": "",
        "sub_value": "",
        "sub_accessibility": "",
        "review_count": ratings_total,        # GOOGLE total reviews
        "review_source": "Google",
        "review_insight": "",
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
    return normalize_row(row)

def fetch_for_center_keyword(lat, lng, radius_m, keyword, seen, rows_by_pid):
    """
    Fetch TextSearch pages for (center, keyword), enrich with Details, and merge.
    """
    data = places_text_search(keyword, lat, lng, radius_m, page_token=None)
    while True:
        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            print(f"[{keyword}] TextSearch status: {status} {data.get('error_message','')}", file=sys.stderr)
            break

        for it in data.get("results", []):
            pid = it.get("place_id")
            if not pid:
                continue

            # If we've never seen this PID, or we might improve the record, pull details.
            need_details = (pid not in rows_by_pid) or True
            if not need_details:
                continue

            time.sleep(0.2)
            det = place_details(pid)
            if det.get("status") != "OK":
                continue
            p = det.get("result", {})
            name = (p.get("name") or "").strip()
            if not name:
                continue

            row = build_row(it, p)
            if pid in rows_by_pid:
                rows_by_pid[pid] = merge_rows(rows_by_pid[pid], row)
            else:
                rows_by_pid[pid] = row
            seen.add(pid)

        # --- improved next_page_token handling ---
        token = data.get("next_page_token")
        if not token:
            break

        # Wait up to ~12s for token to become valid
        advanced = False
        for _ in range(6):
            time.sleep(2)  # 2s * 6 = 12s max
            nxt = places_text_search(keyword, lat, lng, radius_m, page_token=token)
            if nxt.get("status") == "OK":
                data = nxt
                advanced = True
                break
        if not advanced:
            # never became OK; stop
            break

def parse_cli():
    parser = argparse.ArgumentParser(description="Fetch Muscat hotels via Google Places with multi-center, multi-keyword merge.")
    parser.add_argument("--keywords", type=str, default="hotel,resort,guest house,aparthotel,boutique hotel,hostel,camp",
                        help="Comma-separated search keywords (defaults cover common lodging types).")
    # Default centers cover Muscat districts reasonably well
    default_centers = [
        "23.611,58.471",  # Qurum
        "23.585,58.407",  # Al Khuwair / Ghubrah
        "23.620,58.280",  # Al Mouj / Seeb
        "23.600,58.545",  # Ruwi / Mutrah side
        "23.560,58.640",  # Qantab / Bandar Jissah
        "23.570,58.420",  # Bausher / Athaiba
        "23.520,58.385",  # Airport / Al Matar area
        "23.640,58.520",  # Mutrah corniche north
    ]
    parser.add_argument("--centers", type=str, default=";".join(default_centers),
                        help='Semicolon-separated "lat,lng" points to tile the city.')
    parser.add_argument("--radius", type=int, default=8000, help="Search radius per center in meters (default 8000).")
    return parser.parse_args()

def main():
    args = parse_cli()
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    centers = []
    for c in args.centers.split(";"):
        try:
            lat_s, lng_s = c.split(",")
            centers.append((float(lat_s.strip()), float(lng_s.strip())))
        except Exception:
            pass
    radius_m = int(args.radius)

    print(f"Fetching hotels… {len(keywords)} keywords × {len(centers)} centers (radius {radius_m} m)")
    rows_by_pid, seen = {}, set()

    for kw in keywords:
        for (lat, lng) in centers:
            print(f"→ Query '{kw}' @ {lat:.3f},{lng:.3f}")
            fetch_for_center_keyword(lat, lng, radius_m, kw, seen, rows_by_pid)

    rows = list(rows_by_pid.values())
    rows.sort(key=lambda r: (r.get("name",""), r.get("city","")))

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} unique hotels → {OUT_CSV}")
    print(f"Images saved to: {ASSETS_DIR}")

if __name__ == "__main__":
    main()
