#!/usr/bin/env python3
# -*- coding: utf-8 -*- 

import csv, os, time, requests, sys, re, json, argparse
from pathlib import Path
from urllib.parse import urlparse

# ───────────────────────── Basics ─────────────────────────
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not API_KEY:
    print("ERROR: Set GOOGLE_MAPS_API_KEY in your environment.", file=sys.stderr)
    sys.exit(1)

# Project paths (kept same layout as your repo)
ROOT = Path(__file__).resolve().parents[1]   # scripts/ under repo root
SRC_DIR = ROOT / "data" / "sources"
SRC_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = SRC_DIR / "hotels.csv"

# ──────────────────────── Utilities ───────────────────────
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
    try:
        return mapping.get(int(level), "")
    except Exception:
        return ""

def is_http_url(u: str) -> bool:
    try:
        scheme = urlparse(u).scheme.lower()
        return scheme in ("http", "https")
    except Exception:
        return False

# Robust GET with retries/backoff (for Places endpoints only)
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

# ───────────────── Google Places wrappers ─────────────────
def places_text_search(keyword: str, lat: float, lng: float, radius_m: int, page_token=None):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    if page_token:
        params = {"pagetoken": page_token, "key": API_KEY}
    else:
        params = {
            "query": keyword,
            "type": "lodging",
            "location": f"{lat},{lng}",
            "radius": radius_m,
            "key": API_KEY,
        }
    r = http_get(url, params=params, timeout=30)
    return r.json()

def place_details(place_id: str, basic_only: bool):
    """
    Request only non-image fields to reduce cost.
    Excludes 'photos' entirely.
    """
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    # Basic, Contact, and a bit of Atmosphere—no photos.
    fields = [
        "place_id","name","formatted_address","geometry/location",
        "international_phone_number","website","url","business_status",
        "current_opening_hours","editorial_summary","rating","user_ratings_total",
        "price_level"
    ]
    if basic_only:
        # Even cheaper: just core basics (no editorial summary, no hours)
        fields = [
            "place_id","name","formatted_address","geometry/location",
            "international_phone_number","website","url",
            "rating","user_ratings_total","price_level"
        ]
    params = {"place_id": place_id, "fields": ",".join(fields), "key": API_KEY}
    r = http_get(url, params=params, timeout=30)
    return r.json()

def favicon_url_for(site_url: str, size: int = 128) -> str:
    """
    Construct a Google S2 favicon URL (no request here).
    This does not consume Places quota.
    """
    try:
        host = urlparse(site_url).hostname or ""
        if not host:
            return ""
        return f"https://www.google.com/s2/favicons?domain={host}&sz={size}"
    except Exception:
        return ""

# ─────────────────────── CSV schema ───────────────────────
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

# Fill blanks, prefer official website over Maps fallback, keep better review_count
def merge_rows(old, new):
    merged = dict(old)
    for k, v in new.items():
        ov = merged.get(k, "")
        if k == "website":
            if (not ov) or is_maps_fallback(ov):
                if v:
                    merged[k] = v
        elif k == "review_count":
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
    return merged

def build_row(text_item: dict, details: dict, args):
    p = details
    name = (p.get("name") or "").strip()
    slug = slugify(name)

    addr = (p.get("formatted_address") or "").strip()
    loc  = (p.get("geometry") or {}).get("location") or {}
    lat  = loc.get("lat"); lng = loc.get("lng")

    phone  = (p.get("international_phone_number") or "").strip()
    web    = (p.get("website") or "").strip()
    rating = p.get("rating")
    ratings_total = p.get("user_ratings_total") or ""
    price_range = price_level_to_symbols(p.get("price_level"))

    # No photos, no site image scraping: hero_url stays empty
    hero = ""

    # Website fallback to Maps URL if missing
    maps_url = maps_place_url(p.get("place_id",""))
    if not web:
        web = maps_url

    # Optional: favicon URL string (no request performed)
    logo_online = ""
    if not args.no_favicons and web:
        logo_online = favicon_url_for(web, size=128)

    # Hours: store raw JSON if present (free field when requested)
    hours_raw = ""
    if p.get("current_opening_hours") and not args.basic_only:
        try:
            hours_raw = json.dumps(p["current_opening_hours"], ensure_ascii=False)
        except Exception:
            hours_raw = ""

    editorial = ""
    if not args.basic_only:
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
        "maps_url": maps_url,
        "hours_raw": hours_raw,
        "logo_url": logo_online,        # cheap constructed URL; no request
        "hero_url": "",                 # intentionally blank (handled later)
        "image_credit": "",
        "image_source_url": "",
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
        "review_count": ratings_total,
        "review_source": "Google" if ratings_total else "",
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

# One (center, keyword) with guards
def fetch_for_center_keyword(lat, lng, radius_m, keyword, rows_by_pid, args):
    data = places_text_search(keyword, lat, lng, radius_m, page_token=None)
    seen_tokens = set()
    pages_fetched = 0
    last_page_pids = set()

    while True:
        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            print(f"[{keyword}] TextSearch status: {status} {data.get('error_message','')}", file=sys.stderr)
            break

        results = data.get("results", []) or []
        curr_page_pids = set()

        for it in results:
            pid = it.get("place_id")
            if not pid:
                continue
            curr_page_pids.add(pid)

            # Skip already-known PIDs to avoid repeated Details calls
            if pid in rows_by_pid:
                continue

            time.sleep(args.details_throttle_sec)  # gentle on Details quota
            det = place_details(pid, basic_only=args.basic_only)
            if det.get("status") != "OK":
                continue

            p = det.get("result", {}) or {}
            name = (p.get("name") or "").strip()
            if not name:
                continue

            row = build_row(it, p, args)
            if pid in rows_by_pid:
                rows_by_pid[pid] = merge_rows(rows_by_pid[pid], row)
            else:
                rows_by_pid[pid] = row

            if len(rows_by_pid) % 25 == 0:
                print(f"[progress] {len(rows_by_pid)} unique places so far…")

            if args.max_places and len(rows_by_pid) >= args.max_places:
                print(f"[guard] Reached --max-places={args.max_places}; stopping this query.")
                return

        if curr_page_pids and curr_page_pids == last_page_pids:
            print("[guard] Duplicate page detected; breaking pagination loop.")
            break
        last_page_pids = curr_page_pids

        pages_fetched += 1
        if args.max_pages_per_query and pages_fetched >= args.max_pages_per_query:
            break

        token = data.get("next_page_token")
        if not token:
            break
        if token in seen_tokens:
            print("[guard] Seen this next_page_token already; breaking to avoid loop.")
            break
        seen_tokens.add(token)

        # Wait up to ~12s for token to mature
        advanced = False
        for _ in range(6):
            time.sleep(2)
            nxt = places_text_search(keyword, lat, lng, radius_m, page_token=token)
            stat = nxt.get("status")
            if stat == "OK":
                data = nxt
                advanced = True
                break
            elif stat in ("INVALID_REQUEST", "UNKNOWN_ERROR"):
                continue
            elif stat in ("OVER_QUERY_LIMIT", "REQUEST_DENIED"):
                print(f"[warn] {stat} during pagination; stopping this query.")
                advanced = False
                break
            else:
                print(f"[warn] Pagination stopped with status={stat}")
                advanced = False
                break

        if not advanced:
            break

# ──────────────────────── CLI / Main ─────────────────────
def parse_cli():
    parser = argparse.ArgumentParser(
        description="Fetch Muscat hotels via Google Places with low-cost, image-free details."
    )
    parser.add_argument(
        "--keywords",
        type=str,
        default="hotel,resort,guest house,aparthotel,boutique hotel,hostel,camp",
        help="Comma-separated search keywords."
    )
    default_centers = [
        "23.611,58.471",  # Qurum
        "23.585,58.407",  # Al Khuwair / Ghubrah
        "23.620,58.280",  # Al Mouj / Seeb
        "23.600,58.545",  # Ruwi / Mutrah
        "23.560,58.640",  # Qantab / Bandar Jissah
        "23.570,58.420",  # Bausher / Athaiba
        "23.520,58.385",  # Airport / Al Matar
        "23.640,58.520",  # Mutrah corniche north
    ]
    parser.add_argument("--centers", type=str, default=";".join(default_centers),
                        help='Semicolon-separated "lat,lng" points to tile the city.')
    parser.add_argument("--radius", type=int, default=8000, help="Search radius per center in meters.")
    parser.add_argument("--max-pages-per-query", type=int, default=3, help="Max pages per (keyword,center).")
    parser.add_argument("--max-places", type=int, default=100, help="Stop after N unique places overall.")
    parser.add_argument("--wall-timeout-sec", type=int, default=1200, help="Abort run after this many seconds.")

    # Cost/latency controls:
    parser.add_argument("--basic-only", action="store_true",
                        help="Request only core detail fields (cheapest)—no hours/editorial.")
    parser.add_argument("--details-throttle-sec", type=float, default=0.2,
                        help="Sleep seconds between Place Details calls.")

    # Cosmetic (free) favicon string:
    parser.add_argument("--no-favicons", action="store_true",
                        help="Do not include Google S2 favicon URL in logo_url.")
    return parser.parse_args()

def main():
    args = parse_cli()
    start_ts = time.time()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    centers = []
    for c in args.centers.split(";"):
        try:
            lat_s, lng_s = c.split(",")
            centers.append((float(lat_s.strip()), float(lng_s.strip())))
        except Exception:
            pass
    radius_m = int(args.radius)

    print(f"Fetching hotels (image-free)… {len(keywords)} keywords × {len(centers)} centers (radius {radius_m} m, max={args.max_places}, basic_only={args.basic_only})")
    rows_by_pid = {}
    stop_all = False

    for kw in keywords:
        for (lat, lng) in centers:
            if args.wall_timeout_sec and (time.time() - start_ts) > args.wall_timeout_sec:
                print("[guard] Wall timeout reached; stopping…")
                stop_all = True
                break
            if args.max_places and len(rows_by_pid) >= args.max_places:
                stop_all = True
                break
            print(f"→ Query '{kw}' @ {lat:.3f},{lng:.3f}")
            fetch_for_center_keyword(lat, lng, radius_m, kw, rows_by_pid, args)
            if args.max_places and len(rows_by_pid) >= args.max_places:
                stop_all = True
                break
        if stop_all:
            break

    rows = list(rows_by_pid.values())
    rows.sort(key=lambda r: (r.get("name",""), r.get("city","")))

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} unique hotels → {OUT_CSV}")
    print("Note: hero_url intentionally left blank. Use your enrichment/cache steps later to add images.")

if __name__ == "__main__":
    main()
