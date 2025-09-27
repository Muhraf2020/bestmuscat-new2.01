#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv, os, time, requests, sys, re, json, argparse, mimetypes
from pathlib import Path
from urllib.parse import urljoin, urlparse

# ───────────────────────── Basics ─────────────────────────
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not API_KEY:
    print("ERROR: Set GOOGLE_MAPS_API_KEY in your environment.", file=sys.stderr)
    sys.exit(1)

# Project paths (adjust if your tree differs)
ROOT = Path(__file__).resolve().parents[1]   # scripts/ under repo root
SRC_DIR = ROOT / "data" / "sources"
SRC_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = SRC_DIR / "hotels.csv"

ASSETS_DIR = ROOT / "assets" / "hotels"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

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
    return mapping.get(level, "")

def is_http_url(u: str) -> bool:
    try:
        scheme = urlparse(u).scheme.lower()
        return scheme in ("http", "https")
    except Exception:
        return False

# Robust GET/HEAD with retries/backoff
def http_get(url, params=None, timeout=30, allow_redirects=True, max_retries=3, backoff=1.5, method="GET"):
    attempt = 0
    while True:
        try:
            if method == "HEAD":
                r = requests.head(url, params=params, timeout=timeout, allow_redirects=allow_redirects)
            else:
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

def place_details(place_id: str):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = [
        "place_id","name","formatted_address","geometry/location",
        "international_phone_number","website","url","business_status",
        "current_opening_hours","editorial_summary","rating","user_ratings_total",
        "price_level","photos"
    ]
    params = {"place_id": place_id, "fields": ",".join(fields), "key": API_KEY}
    r = http_get(url, params=params, timeout=30)
    return r.json()

def choose_best_photo(photos):
    """Prefer a landscape image (width >= height), else first."""
    if not photos:
        return None
    landscapes = [p for p in photos if (p.get("width",0) >= p.get("height",0))]
    pick = landscapes[0] if landscapes else photos[0]
    return pick.get("photo_reference")

# ---------- Photos: local file OR online URL ----------
def download_photo(photo_ref: str, out_path: Path, maxwidth=1600):
    """
    Save image locally; returns Path (with inferred extension) or False.
    """
    if not photo_ref:
        return False
    base = "https://maps.googleapis.com/maps/api/place/photo"
    qs = {"photoreference": photo_ref, "maxwidth": str(maxwidth), "key": API_KEY}
    resp = http_get(base, params=qs, timeout=60, allow_redirects=True, max_retries=3)
    if resp.status_code == 200 and resp.content:
        ct = resp.headers.get("Content-Type", "")
        ext = mimetypes.guess_extension(ct) or ".jpg"
        out = out_path.with_suffix(ext)
        out.write_bytes(resp.content)
        return out
    return False

def resolve_photo_cdn_url(photo_ref: str, maxwidth=1600):
    """
    Resolve a stable googleusercontent.com CDN URL (no API key in URL).
    """
    if not photo_ref:
        return ""
    base = "https://maps.googleapis.com/maps/api/place/photo"
    qs = {"photoreference": photo_ref, "maxwidth": str(maxwidth), "key": API_KEY}

    # Try no-redirect first to read Location
    try:
        r = http_get(base, params=qs, timeout=30, allow_redirects=False)
        if r.status_code in (302, 303) and r.headers.get("Location"):
            return r.headers["Location"]
    except Exception:
        pass

    # Fallback: follow redirects and use final URL
    try:
        r2 = http_get(base, params=qs, timeout=60, allow_redirects=True)
        return r2.url
    except Exception:
        return ""

# ---------- Website image & favicon ----------
_META_IMG_RE = re.compile(
    r'<meta[^>]+(?:property|name)\s*=\s*["\'](?:og:image|twitter:image)["\'][^>]*content\s*=\s*["\']([^"\']+)["\']',
    re.I
)
_LINK_IMG_RE = re.compile(
    r'<link[^>]+rel\s*=\s*["\'][^"\']*(?:image_src|apple-touch-icon|icon)[^"\']*["\'][^>]*href\s*=\s*["\']([^"\']+)["\']',
    re.I
)

def resolve_site_social_image(site_url: str) -> str:
    """
    Try to get a 'hero' image from the website:
    1) <meta property="og:image"> or <meta name="twitter:image">
    2) <link rel="image_src">, <link rel="apple-touch-icon">, <link rel="icon">
    Returns absolute URL or "".
    """
    if not is_http_url(site_url):
        return ""
    try:
        resp = http_get(site_url, timeout=20, allow_redirects=True)
        html = resp.text[:300_000]  # cap parse window
        # Prefer OG/Twitter first
        m = _META_IMG_RE.search(html)
        if m:
            return urljoin(resp.url, m.group(1).strip())
        # Fallback to link rels
        m2 = _LINK_IMG_RE.search(html)
        if m2:
            return urljoin(resp.url, m2.group(1).strip())
    except Exception:
        return ""
    return ""

def guess_favicon(site_url: str, size: int = 128) -> str:
    """
    Return a stable online favicon for the domain using Google S2 favicons.
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

# Fill blanks, prefer official website over Maps fallback, keep better hero/review_count
def merge_rows(old, new):
    merged = dict(old)
    for k, v in new.items():
        ov = merged.get(k, "")
        if k == "website":
            if (not ov) or is_maps_fallback(ov):
                if v:
                    merged[k] = v
        elif k == "hero_url":
            if not ov and v:
                merged[k] = v
        elif k == "logo_url":
            if not ov and v:
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

    # Photos: prefer Details photos, else fall back to TextSearch photos
    details_photos = p.get("photos") or []
    seed_photos = text_item.get("photos") or []
    chosen_ref = choose_best_photo(details_photos) or choose_best_photo(seed_photos)

    # Decide hero image source: Google Photo (local/online) and/or Website social image
    hero = ""
    site_image = ""

    # If the place has a real website (not the maps fallback), consider its social image
    has_real_site = is_http_url(web) and not is_maps_fallback(web)

    if args.prefer_site_image and has_real_site:
        site_image = resolve_site_social_image(web)
        if site_image:
            hero = site_image

    if not hero and chosen_ref and not args.no_photos:
        if args.online_photos:
            cdn_url = resolve_photo_cdn_url(chosen_ref, maxwidth=1600)
            if cdn_url:
                hero = cdn_url
        else:
            out_path = ASSETS_DIR / f"{slug}"
            saved = download_photo(chosen_ref, out_path, maxwidth=1600)
            if saved:
                hero = str(saved.relative_to(ROOT)).replace("\\","/")

    # Still no hero? Try website social image as a fallback
    if not hero and has_real_site:
        site_image = site_image or resolve_site_social_image(web)
        if site_image:
            hero = site_image

    # Website fallback to Maps URL if missing
    maps_url = maps_place_url(p.get("place_id",""))
    if not web:
        web = maps_url

    # Always set a stable online favicon into logo_url if we have a real site
    logo_online = guess_favicon(web) if has_real_site else ""

    # Hours: store raw JSON
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
        "maps_url": maps_url,
        "hours_raw": hours_raw,
        "logo_url": logo_online,                 # online favicon (nice fallback)
        "hero_url": hero,                        # local path OR online URL (Google CDN or site)
        "image_credit": "Image © Google" if (hero and "googleusercontent.com" in hero) else "",
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
        "review_count": ratings_total,
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

# One (center, keyword) with strong guards
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

            # Fetch Details only if this PID is new (prevents re-fetch spam)
            if pid in rows_by_pid:
                continue

            time.sleep(0.2)  # be gentle with Details quota
            det = place_details(pid)
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

            # Optional: progress heartbeat
            if len(rows_by_pid) % 25 == 0:
                print(f"[progress] {len(rows_by_pid)} unique places so far…")

            # Global hard cap
            if args.max_places and len(rows_by_pid) >= args.max_places:
                print(f"[guard] Reached --max-places={args.max_places}; stopping this query.")
                return

        # Duplicate page guard
        if curr_page_pids and curr_page_pids == last_page_pids:
            print("[guard] Duplicate page detected; breaking pagination loop.")
            break
        last_page_pids = curr_page_pids

        # Page count guard
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
        description="Fetch Muscat hotels via Google Places with multi-center, multi-keyword merge (safe guards)."
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
        "23.600,58.545",  # Ruwi / Mutrah side
        "23.560,58.640",  # Qantab / Bandar Jissah
        "23.570,58.420",  # Bausher / Athaiba
        "23.520,58.385",  # Airport / Al Matar area
        "23.640,58.520",  # Mutrah corniche north
    ]
    parser.add_argument(
        "--centers",
        type=str,
        default=";".join(default_centers),
        help='Semicolon-separated "lat,lng" points to tile the city.'
    )
    parser.add_argument("--radius", type=int, default=8000, help="Search radius per center in meters.")
    parser.add_argument("--no-photos", action="store_true", help="Skip photo handling (fastest).")
    parser.add_argument("--online-photos", action="store_true",
                        help="Do not download; store the final googleusercontent.com image URL in hero_url.")
    parser.add_argument("--prefer-site-image", action="store_true",
                        help="Prefer website social image (og:image / twitter:image) over Google Photo when available.")
    parser.add_argument("--max-pages-per-query", type=int, default=3, help="Max pages per (keyword,center).")
    parser.add_argument("--max-places", type=int, default=100, help="Stop after N unique places overall.")
    parser.add_argument("--wall-timeout-sec", type=int, default=1200, help="Abort run after this many seconds.")
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

    print(f"Fetching hotels… {len(keywords)} keywords × {len(centers)} centers (radius {radius_m} m, max={args.max_places}, online_photos={args.online_photos}, prefer_site_image={args.prefer_site_image})")
    rows_by_pid = {}
    stop_all = False

    for kw in keywords:
        for (lat, lng) in centers:
            # Wall clock guard
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
    if args.online_photos:
        print("Images are referenced via googleusercontent.com URLs (not downloaded).")
    else:
        print(f"Images saved to: {ASSETS_DIR}")

if __name__ == "__main__":
    main()
