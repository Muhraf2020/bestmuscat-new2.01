#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enrich hotels CSV with free web signals (no Google paid APIs).

This version:
- Finds hero_url from official site (og:image, twitter:image, common hero <img> patterns)
- Falls back to Wikidata P18, or Wikipedia page image if Wikidata/QID missing
- Rejects logos/icons/pixels as hero images (by filename pattern, MIME, and size)
- Final fallback: a curated set of Muscat city images (can be replaced with your local assets)
- Keeps everything free; does not download images, only stores URLs + credits
"""

from __future__ import annotations
import csv, re, time, json, hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import html
import requests
from bs4 import BeautifulSoup

# ----- Config -----
HEADERS = {
    "User-Agent": "BestMuscatBot/1.1 (+https://bestmuscat.com/; admin@bestmuscat.com)"
}
TIMEOUT = 25
PAUSE = 0.8
RETRIES = 2
MAX_BYTES = 1_000_000  # cap parsed body to ~1MB

# Muscat International Airport (MCT)
MCT_LAT, MCT_LNG = 23.5933, 58.2844


# ----- Small utils -----
def is_http(u: Optional[str]) -> bool:
    return isinstance(u, str) and u.lower().startswith(("http://", "https://"))

def clean(s: Any) -> str:
    return (s or "").strip()

def absolute(base: str, url: str) -> str:
    from urllib.parse import urljoin
    return urljoin(base, url)

def domain_root(url: str) -> Optional[str]:
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return None

def session_with_retries() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s

def fetch(sess: requests.Session, url: str) -> Optional[requests.Response]:
    if not is_http(url):
        return None
    for attempt in range(RETRIES + 1):
        try:
            r = sess.get(url, timeout=TIMEOUT, allow_redirects=True)
            r.raise_for_status()
            # Trim to reduce parsing cost; keep head + some body
            r._content = r.content[:MAX_BYTES]
            return r
        except Exception:
            if attempt >= RETRIES:
                return None
            time.sleep(0.8 * (attempt + 1))
    return None


# ----- HTML extraction helpers -----
def jsonld_blocks(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, list):
                out.extend([d for d in data if isinstance(d, dict)])
            elif isinstance(data, dict):
                out.append(data)
        except Exception:
            continue
    return out

def first_hotel_like(ldjson_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    # Prefer Hotel / LodgingBusiness nodes
    for obj in ldjson_list:
        t = clean(obj.get("@type"))
        if not t and "@graph" in obj:
            for node in obj["@graph"]:
                tt = clean(node.get("@type"))
                if str(tt).lower() in {"hotel", "lodgingbusiness"}:
                    return node
        if str(t).lower() in {"hotel", "lodgingbusiness"}:
            return obj
    # Fallback: any with amenityFeature or starRating
    for obj in ldjson_list:
        if "amenityFeature" in obj or "starRating" in obj:
            return obj
    return None

def meta_desc(soup: BeautifulSoup) -> Optional[str]:
    for sel in [('meta[name="description"]', "content"),
                ('meta[property="og:description"]', "content")]:
        for tag in soup.select(sel[0]):
            val = clean(tag.get(sel[1]))
            if val:
                return val
    return None

def first_paragraph(soup: BeautifulSoup) -> Optional[str]:
    for p in soup.find_all("p"):
        txt = clean(p.get_text(" ", strip=True))
        if len(txt) > 60:
            return txt
    return None

def clamp_text(s: str, maxlen: int) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= maxlen else s[:maxlen].rsplit(" ", 1)[0] + "…"

def detect_star_from_text(txt: str) -> Optional[str]:
    t = txt.lower()
    m = re.search(r"(\d)\s*[-\s]?star", t)
    if m:
        return m.group(1)
    words = {"five": "5", "four": "4", "three": "3"}
    for w, d in words.items():
        if re.search(rf"\b{w}\s*[-\s]?star", t):
            return d
    return None

def extract_amenities_from_text(txt: str) -> List[str]:
    keys = {
        "free wifi": ["free wifi", "complimentary wifi", "wi-fi", "internet"],
        "pool": ["pool", "swimming pool", "infinity pool"],
        "spa": ["spa", "sauna", "steam"],
        "beach": ["private beach", "beach access", "beachfront"],
        "parking": ["free parking", "parking available", "valet parking"],
        "gym": ["gym", "fitness centre", "fitness center"],
        "breakfast": ["free breakfast", "breakfast included", "buffet breakfast"],
        "airport shuttle": ["airport shuttle", "airport transfer"],
    }
    found = set()
    lt = txt.lower()
    for label, cues in keys.items():
        if any(c in lt for c in cues):
            found.add(label)
    return sorted(found)


# ----- Hero-quality filters & Muscat stock -----
LOGO_PAT = re.compile(r"(?:^|/)(?:logo|logos?|brand|mark|icon|icons?|favicon|sprite|social)(?:[-_./]|$)", re.I)
SVG_OR_ICO_PAT = re.compile(r"\.(?:svg|ico)(?:$|\?)", re.I)
SOCIAL_PIXEL_PAT = re.compile(r"(?:facebook\.com/|/facebook\.png|/pixel\.gif|/analytics)", re.I)

def looks_like_logo_or_icon(url: str) -> bool:
    u = url or ""
    return bool(
        LOGO_PAT.search(u) or
        SVG_OR_ICO_PAT.search(u) or
        SOCIAL_PIXEL_PAT.search(u)
    )

def acceptable_content_type(ct: Optional[str]) -> bool:
    # Only accept bitmap images; reject vector/svg and anything non-image
    if not ct: return False
    ct = ct.lower().strip()
    if not ct.startswith("image/"): return False
    if "svg" in ct: return False
    return True

def big_enough(bytes_len: Optional[int]) -> bool:
    # Heuristic: require at least ~8KB; social badges/icons are often tiny
    try:
        return int(bytes_len or 0) >= 8000
    except Exception:
        return False

def fetch_head_like(sess: requests.Session, url: str) -> Tuple[Optional[str], Optional[int]]:
    """Best-effort content-type and size without downloading too much."""
    try:
        r = sess.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True)
        ct = r.headers.get("Content-Type")
        cl = r.headers.get("Content-Length")
        r.close()
        return (ct, int(cl) if cl and cl.isdigit() else None)
    except Exception:
        return (None, None)

# Curated, safe-to-use Muscat stock images (replace with your own if you prefer)
MUSCAT_STOCK = [
    # Wikimedia Commons originals (examples)
    "https://upload.wikimedia.org/wikipedia/commons/4/4e/Muttrah_Corniche%2C_Muscat.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/5/5d/Sultan_Qaboos_Grand_Mosque%2C_Muscat.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/0/0d/Riyam_Park_Incense_Burner%2C_Muscat.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/0/0d/Al_Alam_Palace%2C_Oman.jpg",
    # If you have local assets, point to them instead, e.g.:
    # "/assets/images/stock/muscat-1.webp",
    # "/assets/images/stock/muscat-2.webp",
]

def pick_muscat_stock(key: str = "") -> Optional[str]:
    """Deterministically pick a stock image based on a key (e.g., slug), for variety."""
    if not MUSCAT_STOCK:
        return None
    h = int(hashlib.sha1((key or 'muscat').encode('utf-8')).hexdigest(), 16)
    return MUSCAT_STOCK[h % len(MUSCAT_STOCK)]


# ----- Image helpers (OFFICIAL SITE) -----
def select_from_srcset(attr: str) -> Optional[str]:
    # Pick the last (usually largest) url in a srcset
    try:
        parts = [p.strip() for p in attr.split(",")]
        if not parts:
            return None
        # "url 2x" or "url 800w"
        last = parts[-1].split()[0]
        return last
    except Exception:
        return None

def find_site_hero_url(sess: requests.Session, soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Return a 'photo-like' hero URL from the official site, rejecting logos/icons/pixels."""
    # 1) Meta tags first
    metas: List[str] = []
    for name in ("property", "name"):
        for key in ("og:image", "twitter:image", "twitter:image:src"):
            for tag in soup.find_all("meta", {name: key}):
                val = clean(tag.get("content"))
                if val:
                    metas.append(absolute(base_url, html.unescape(val)))

    # 2) link[rel=image_src]
    link_tag = soup.find("link", {"rel": "image_src"})
    if link_tag and link_tag.get("href"):
        metas.append(absolute(base_url, link_tag["href"].strip()))

    # 3) Hero-ish <img> heuristics
    candidates: List[str] = []
    hero_words = ("hero", "banner", "header", "masthead", "slideshow", "carousel")
    for img in soup.find_all("img"):
        classes = " ".join(img.get("class") or []).lower()
        alt = (img.get("alt") or "").lower()
        attrs = " ".join([classes, alt])
        if any(w in attrs for w in hero_words):
            for key in ("data-src", "data-original", "data-lazy", "src", "data-url"):
                val = img.get(key)
                if val:
                    candidates.append(val)
            if img.get("srcset"):
                ss = select_from_srcset(img["srcset"])
                if ss:
                    candidates.append(ss)

    # 4) Fallback: first non-tiny image anywhere
    if not candidates:
        for img in soup.find_all("img"):
            for key in ("data-src", "data-original", "src"):
                val = img.get(key)
                if val:
                    candidates.append(val)
                    break
            if img.get("srcset"):
                ss = select_from_srcset(img["srcset"])
                if ss:
                    candidates.append(ss)

    # Normalize & de-dup
    all_cands, seen = [], set()
    for href in [*metas, *candidates]:
        if not href:
            continue
        url = absolute(base_url, html.unescape(href.strip()))
        if not is_http(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        all_cands.append(url)

    # Filter out obvious logos/icons/pixels by pattern
    filtered = [u for u in all_cands if not looks_like_logo_or_icon(u)]

    # Validate by MIME/size; pick the first "photo-like"
    for u in filtered:
        ct, size = fetch_head_like(sess, u)
        if acceptable_content_type(ct) and big_enough(size):
            return u

    # Last resort: accept if MIME is image/* (non-SVG), even if size unknown
    for u in filtered:
        ct, _ = fetch_head_like(sess, u)
        if acceptable_content_type(ct):
            return u

    return None


# ----- Wikidata / Wikipedia fallbacks (FREE) -----
WD_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WP_SEARCH = "https://en.wikipedia.org/w/api.php"
WP_PAGEIMAGE = "https://www.en.wikipedia.org/w/api.php"

def wikidata_main_image(sess: requests.Session, qid: str) -> Optional[str]:
    if not qid:
        return None
    try:
        r = sess.get(WD_ENTITY.format(qid=qid), timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        ent = next(iter(r.json().get("entities", {}).values()))
        claims = ent.get("claims", {})
        if "P18" in claims:
            file_name = claims["P18"][0]["mainsnak"]["datavalue"]["value"]
            return f"https://commons.wikimedia.org/wiki/Special:FilePath/{str(file_name).replace(' ', '_')}"
    except Exception:
        return None
    return None

def wikipedia_page_image(sess: requests.Session, name: str, city: str) -> Optional[str]:
    """Find a likely Wikipedia article then fetch its page image (original)."""
    try:
        # 1) search
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": f"{name} {city}".strip(),
            "srlimit": 1,
            "srprop": ""
        }
        r = sess.get(WP_SEARCH, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        hits = (r.json().get("query") or {}).get("search") or []
        if not hits:
            return None
        title = hits[0].get("title")
        if not title:
            return None

        # 2) get pageimage/original
        params2 = {
            "action": "query",
            "format": "json",
            "prop": "pageimages|pageprops",
            "piprop": "original",
            "titles": title
        }
        r2 = sess.get(WP_PAGEIMAGE, params=params2, timeout=TIMEOUT)
        r2.raise_for_status()
        pages = (r2.json().get("query") or {}).get("pages") or {}
        for _, page in pages.items():
            orig = (page.get("original") or {}).get("source")
            if orig and is_http(orig):
                return orig
    except Exception:
        return None
    return None


# ----- Main enrichment per row -----
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0088
    from math import radians, sin, cos, asin, sqrt
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2) ** 2
    return round(2 * R * asin(sqrt(a)), 2)

def wikidata_qid(sess: requests.Session, name: str, city: str) -> Optional[str]:
    params = {
        "action": "wbsearchentities",
        "format": "json",
        "language": "en",
        "search": f"{name} {city}".strip(),
        "type": "item",
        "limit": 1,
    }
    try:
        r = sess.get("https://www.wikidata.org/w/api.php", params=params, timeout=TIMEOUT)
        if r.ok:
            j = r.json()
            hits = j.get("search") or []
            if hits:
                return hits[0].get("id")
    except Exception:
        return None
    return None

def find_icons(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    icons = []
    for sel in [
        ('link[rel="icon"]', "href"),
        ('link[rel="shortcut icon"]', "href"),
        ('link[rel="apple-touch-icon"]', "href"),
        ('link[rel="apple-touch-icon-precomposed"]', "href"),
        ('link[rel="mask-icon"]', "href"),
    ]:
        for tag in soup.select(sel[0]):
            href = tag.get(sel[1])
            if href:
                icons.append(href.strip())
    for href in icons:
        absu = absolute(base_url, href)
        if is_http(absu):
            return absu
    root = domain_root(base_url)
    if root:
        return root.rstrip("/") + "/favicon.ico"
    return None

def enrich_row(sess: requests.Session, row: Dict[str, str]) -> Dict[str, str]:
    name = clean(row.get("name"))
    city = clean(row.get("city"))
    lat  = row.get("lat")
    lng  = row.get("lng")
    latf = float(lat) if lat not in (None, "",) else None
    lngf = float(lng) if lng not in (None, "",) else None

    site = clean(row.get("website") or row.get("url"))
    page_resp = fetch(sess, site) if is_http(site) else None
    soup = BeautifulSoup(page_resp.text, "html.parser") if page_resp else None
    ld = jsonld_blocks(soup) if soup else []
    hotel_ld = first_hotel_like(ld) if ld else None

    # logo_url
    if not clean(row.get("logo_url")) and soup and page_resp is not None:
        icon = find_icons(soup, page_resp.url)
        if is_http(icon):
            row["logo_url"] = icon

    # about_short / about_long
    if (not clean(row.get("about_short")) or not clean(row.get("about_long"))) and soup:
        md = meta_desc(soup) or ""
        para = first_paragraph(soup) or ""
        if not clean(row.get("about_short")) and md:
            row["about_short"] = clamp_text(md, 200)
        if not clean(row.get("about_long")):
            long_txt = (md + " " + para).strip() if md or para else ""
            if long_txt:
                row["about_long"] = clamp_text(long_txt, 600)

    # JSON-LD enrichments
    if hotel_ld:
        if not clean(row.get("price_range")) and hotel_ld.get("priceRange"):
            row["price_range"] = clean(hotel_ld.get("priceRange"))
        if not clean(row.get("star_rating")):
            sr = hotel_ld.get("starRating") or {}
            if isinstance(sr, dict):
                val = sr.get("ratingValue") or sr.get("rating")
                if val:
                    row["star_rating"] = str(val).strip()
        if not clean(row.get("checkin_time")) and hotel_ld.get("checkinTime"):
            row["checkin_time"] = clean(hotel_ld.get("checkinTime"))
        if not clean(row.get("checkout_time")) and hotel_ld.get("checkoutTime"):
            row["checkout_time"] = clean(hotel_ld.get("checkoutTime"))

        # amenities
        amen = []
        af = hotel_ld.get("amenityFeature")
        if isinstance(af, list):
            for it in af:
                if isinstance(it, dict):
                    nm = clean(it.get("name"))
                    if nm:
                        amen.append(nm)
        amen = list(dict.fromkeys(amen))
        page_text = soup.get_text(" ", strip=True) if soup else ""
        amen_k = extract_amenities_from_text(page_text)
        amen_all = ";".join(sorted(set([*amen, *amen_k]))) if (amen or amen_k) else ""
        if amen_all:
            if not clean(row.get("hotel_amenities")):
                row["hotel_amenities"] = amen_all
            if not clean(row.get("amenities")):
                row["amenities"] = amen_all

    # star_rating fallback via text
    if not clean(row.get("star_rating")) and soup:
        sr_txt = detect_star_from_text(soup.get_text(" ", strip=True))
        if sr_txt:
            row["star_rating"] = sr_txt

    # breakfast_included / parking heuristics
    if soup:
        txt = soup.get_text(" ", strip=True).lower()
        if not clean(row.get("breakfast_included")):
            if ("breakfast included" in txt or "free breakfast" in txt or "complimentary breakfast" in txt):
                row["breakfast_included"] = "Yes"
        if not clean(row.get("parking")):
            if ("free parking" in txt or "parking available" in txt or "valet parking" in txt):
                row["parking"] = "Yes"

    # If an existing hero_url looks like a logo/icon/pixel, wipe it so we can refill
    if clean(row.get("hero_url")) and looks_like_logo_or_icon(row["hero_url"]):
        row["hero_url"] = ""

    # ----------------- HERO IMAGE PIPELINE -----------------
    if not clean(row.get("hero_url")):
        # (1) Official site meta/hero <img>
        if soup and page_resp is not None:
            site_hero = find_site_hero_url(sess, soup, page_resp.url)
            if is_http(site_hero) and not looks_like_logo_or_icon(site_hero):
                row["hero_url"] = site_hero
                row.setdefault("image_credit", "Official site")
                row.setdefault("image_source_url", page_resp.url)

        # (2) Wikidata main image if still missing (free)
        if not clean(row.get("hero_url")):
            qid = clean(row.get("wikidata_id"))
            if not qid and name:
                qid = wikidata_qid(sess, name, city) or ""
                if qid:
                    row["wikidata_id"] = qid
            if qid:
                wdi = wikidata_main_image(sess, qid)
                if is_http(wdi) and not looks_like_logo_or_icon(wdi):
                    row["hero_url"] = wdi
                    row.setdefault("image_credit", "Wikimedia Commons")
                    row.setdefault("image_source_url", wdi)

        # (3) Wikipedia page image if still missing (free)
        if not clean(row.get("hero_url")) and name:
            wpi = wikipedia_page_image(sess, name, city)
            if is_http(wpi) and not looks_like_logo_or_icon(wpi):
                row["hero_url"] = wpi
                row.setdefault("image_credit", "Wikipedia")
                row.setdefault("image_source_url", wpi)

        # (4) Final fallback: curated Muscat city image
        if not clean(row.get("hero_url")):
            stock = pick_muscat_stock(key=name or row.get("slug","") or "")
            if stock:
                row["hero_url"] = stock
                row.setdefault("image_credit", "Muscat stock")
                row.setdefault("image_source_url", stock)
    # -------------------------------------------------------

    # Distance to airport
    if not clean(row.get("distance_to_airport")) and (latf is not None and lngf is not None):
        row["distance_to_airport"] = str(haversine_km(latf, lngf, MCT_LAT, MCT_LNG))

    return row


# ----- CLI / Main -----
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Enrich hotels CSV (free sources only).")
    ap.add_argument("--csv", default="data/sources/hotels.csv",
                    help="Path to hotels CSV (will be updated in place).")
    ap.add_argument("--sleep", type=float, default=PAUSE,
                    help="Pause between rows (seconds).")
    args = ap.parse_args()

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"CSV not found: {path}")

    # Load CSV
    with path.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        fieldnames = rdr.fieldnames or []
        must_have = [
            "logo_url","about_short","about_long","price_range","star_rating",
            "checkin_time","checkout_time","hotel_amenities","amenities",
            "image_credit","image_source_url","wikidata_id","distance_to_airport",
            "breakfast_included","parking","hero_url"
        ]
        rows: List[Dict[str, str]] = []
        for r in rdr:
            for k in must_have:
                r.setdefault(k, "")
            rows.append(r)

    # Enrich
    sess = session_with_retries()
    updated = 0
    for i, row in enumerate(rows, 1):
        try:
            new_row = enrich_row(sess, row)
            if new_row != row:
                updated += 1
                rows[i-1] = new_row
        except Exception:
            # keep going on errors
            pass
        time.sleep(args.sleep)

    # Write back
    out_fields = list(rows[0].keys()) if rows else fieldnames
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Enrichment complete. Rows updated: {updated}/{len(rows)}")

if __name__ == "__main__":
    main()

