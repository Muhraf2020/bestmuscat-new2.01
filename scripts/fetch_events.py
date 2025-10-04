#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fetch Muscat event planners via Google Places (image-free, low-cost).

- Text Search + Details (NO 'photos' field) to keep API cost low
- Constrains results with type=event_planner (plus keywords)
- Writes to data/sources/events.csv
- If events.csv already exists, preserves its header order

Run (example):
  export GOOGLE_MAPS_API_KEY=YOUR_KEY
  python scripts/fetch_events.py --basic-only --max-places 140
"""

import csv, os, time, requests, sys, re, json, argparse
from pathlib import Path
from urllib.parse import urlparse

# ───────────────────────── Basics ─────────────────────────
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not API_KEY:
    print("ERROR: Set GOOGLE_MAPS_API_KEY in your environment.", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]   # repo root (scripts/ under root)
SRC_DIR = ROOT / "data" / "sources"
SRC_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = SRC_DIR / "events.csv"

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

def is_http_url(u: str) -> bool:
    try:
        scheme = urlparse(u).scheme.lower()
        return scheme in ("http", "https")
    except Exception:
        return False

def price_level_to_symbols(level):
    # Rare/undefined for planners; keep for compatibility
    mapping = {0:"$", 1:"$", 2:"$$", 3:"$$$", 4:"$$$$"}
    try:
        return mapping.get(int(level), "")
    except Exception:
        return ""

def http_get(url, params=None, timeout=30, allow_redirects=True, max_retries=3, backoff=1.5):
    """Robust GET with retries/backoff for Places endpoints."""
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

def favicon_url_for(site_url: str, size: int = 128) -> str:
    """Construct a Google S2 favicon URL (string only; no extra request here)."""
    try:
        host = urlparse(site_url).hostname or ""
        if not host:
            return ""
        return f"https://www.google.com/s2/favicons?domain={host}&sz={size}"
    except Exception:
        return ""

# ─────────────────────── CSV schema ───────────────────────
# Default template (used ONLY if OUT_CSV doesn't exist yet).
DEFAULT_HEADERS = [
    "id","slug","name","category","tagline","tags",
    "neighborhood","address","city","country","lat","lng",
    "maps_url","website","phone","url",
    "logo_url","hero_url","image_credit","image_source_url",
    "place_id","osm_type","osm_id","wikidata_id",
    "description","price_range","about_short","about_long","amenities",
    "rating_overall","sub_service","sub_ambience","sub_value","sub_accessibility",
    "review_count","review_source","review_insight","last_updated",
    # Event planner–specific placeholders (blank; enrich later)
    "weddings","corporate_events","birthday_parties","event_decor","catering_coordination",
    "audio_visual","staging","rentals","balloon_decor","flower_arrangement",
    "photography_coordination","videography_coordination","mc_hosting","dj_services",
    "kids_entertainment","ticketing","permits_handling",
    "enquiries_url","portfolio_url","instagram_url","whatsapp"
]

def load_header_order_from_existing_csv(path: Path):
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            rdr = csv.reader(f)
            header = next(rdr, None)
            if header and all(isinstance(h, str) for h in header):
                return header
    except Exception:
        return None
    return None

def normalize_row(d, header_order):
    out = {}
    for k in header_order:
        out[k] = d.get(k, "")
    return out

def merge_rows(old, new):
    """Fill blanks; prefer official website over Maps fallback; keep better review_count."""
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

# ───────────────── Google Places wrappers ─────────────────
def places_text_search(keyword: str, lat: float, lng: float, radius_m: int, page_token=None):
    """
    Text Search for event planners around a center point.
    Constrains by 'type=event_planner' to reduce noise, with keyword support.
    """
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    if page_token:
        params = {"pagetoken": page_token, "key": API_KEY}
    else:
        params = {
            "query": keyword,
            "type": "event_planner",
            "location": f"{lat},{lng}",
            "radius": radius_m,
            "key": API_KEY,
        }
    r = http_get(url, params=params, timeout=30)
    return r.json()

def place_details(place_id: str, basic_only: bool):
    """
    Request ONLY non-image fields to reduce cost. (No 'photos')
    """
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = [
        "place_id","name","formatted_address","geometry/location",
        "international_phone_number","website","url","business_status",
        "current_opening_hours","editorial_summary","rating","user_ratings_total",
        "price_level"
    ]
    if basic_only:
        fields = [
            "place_id","name","formatted_address","geometry/location",
            "international_phone_number","website","url",
            "rating","user_ratings_total","price_level"
        ]
    params = {"place_id": place_id, "fields": ",".join(fields), "key": API_KEY}
    r = http_get(url, params=params, timeout=30)
    return r.json()

# ───────────────────── Row construction ───────────────────
def build_row(text_item: dict, details: dict, args, header_order):
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
    price_range = price_level_to_symbols(p.get("price_level"))  # usually blank

    maps_url = maps_place_url(p.get("place_id",""))
    if not web:
        web = maps_url

    logo_online = ""
    if not args.no_favicons and web:
        logo_online = favicon_url_for(web, size=128)

    editorial = ""
    if not args.basic_only:
        editorial = (p.get("editorial_summary") or {}).get("overview","").strip()

    row_full = {
        "id": p.get("place_id",""),
        "slug": slug,
        "name": name,
        "category": "Events",
        "tagline": editorial[:140] if editorial else "",
        "tags": "events;event planner;wedding;corporate",
        "neighborhood": "",
        "address": addr,
        "city": "Muscat",
        "country": "Oman",
        "lat": f"{lat:.6f}" if isinstance(lat,(int,float)) else "",
        "lng": f"{lng:.6f}" if isinstance(lng,(int,float)) else "",
        "maps_url": maps_url,
        "website": web,
        "phone": phone,
        "url": web,
        "logo_url": logo_online,
        "hero_url": "",                 # intentionally blank (enrich later)
        "image_credit": "",
        "image_source_url": "",
        "place_id": p.get("place_id",""),
        "osm_type": "",
        "osm_id": "",
        "wikidata_id": "",
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
        # Event planner–specific placeholders
        "weddings": "",
        "corporate_events": "",
        "birthday_parties": "",
        "event_decor": "",
        "catering_coordination": "",
        "audio_visual": "",
        "staging": "",
        "rentals": "",
        "balloon_decor": "",
        "flower_arrangement": "",
        "photography_coordination": "",
        "videography_coordination": "",
        "mc_hosting": "",
        "dj_services": "",
        "kids_entertainment": "",
        "ticketing": "",
        "permits_handling": "",
        "enquiries_url": "",
        "portfolio_url": "",
        "instagram_url": "",
        "whatsapp": "",
    }
    return normalize_row(row_full, header_order)

# ─────────────────────── Fetch loop ───────────────────────
def fetch_for_center_keyword(lat, lng, radius_m, keyword, rows_by_pid, args, header_order):
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

            row = build_row(it, p, args, header_order)
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

# ─────────────────────── CLI / Main ───────────────────────
def parse_cli():
    parser = argparse.ArgumentParser(
        description="Fetch Muscat event planners via Google Places (image-free, low-cost)."
    )
    parser.add_argument(
        "--keywords",
        type=str,
        default="event planner,event planning,wedding planner,party planner,corporate events,event management,event decor,balloon decor,stage rentals,audio visual",
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
    parser.add_argument("--radius", type=int, default=6000, help="Search radius per center in meters.")
    parser.add_argument("--max-pages-per-query", type=int, default=2, help="Max pages per (keyword,center).")
    parser.add_argument("--max-places", type=int, default=140, help="Stop after N unique places overall.")
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

    # Preserve existing header order if CSV exists, else use default template
    header_order = load_header_order_from_existing_csv(OUT_CSV) or DEFAULT_HEADERS

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    centers = []
    for c in args.centers.split(";"):
        try:
            lat_s, lng_s = c.split(",")
            centers.append((float(lat_s.strip()), float(lng_s.strip())))
        except Exception:
            pass
    radius_m = int(args.radius)

    print(f"Fetching events (image-free)… {len(keywords)} keywords × {len(centers)} centers "
          f"(radius {radius_m} m, max={args.max_places}, basic_only={args.basic_only})")
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
            fetch_for_center_keyword(lat, lng, radius_m, kw, rows_by_pid, args, header_order)
            if args.max_places and len(rows_by_pid) >= args.max_places:
                stop_all = True
                break
        if stop_all:
            break

    rows = list(rows_by_pid.values())
    rows.sort(key=lambda r: (r.get("name",""), r.get("city","")))

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header_order)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Wrote {len(rows)} unique event planners → {OUT_CSV}")
    print("Note: hero_url intentionally left blank. Use enrichment/cache steps later to add images.")

if __name__ == "__main__":
    main()
