#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enrich malls CSV with free web signals (no paid APIs).

It:
- Finds hero_url from official site (og:image, twitter:image, hero-ish <img>), rejecting logos/pixels
- Falls back to Wikipedia page image (free) if site image missing
- Final fallback: curated Muscat stock image list (swap to local assets if you prefer)
- Extracts about_short / about_long from meta/first paragraph
- Detects favicon for logo_url when missing
- Detects useful links: store directory / mall map / events / offers / parking info
- Heuristically flags amenities: parking, valet, cinema, food court, supermarket, pharmacy,
  kids area / play area, prayer room, wheelchair access, ATM, free wifi
- Aggregates a semicolon-separated `amenities` string
- DOES NOT download images; uses only lightweight HEAD/GET checks

Run:
  python scripts/enrich/enrich_malls.py --csv data/sources/malls.csv
"""

from __future__ import annotations
import csv, re, time, json, hashlib, html
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import requests
from bs4 import BeautifulSoup

# ---------- Config ----------
HEADERS = {
    "User-Agent": "BestMuscatBot/1.1 (+https://bestmuscat.com/; admin@bestmuscat.com)"
}
TIMEOUT = 25
RETRIES = 2
PAUSE = 0.8
MAX_BYTES = 1_000_000  # keep parsing cheap

# ---------- Small utils ----------
def clean(s): return (s or "").strip()
def is_http(u: Optional[str]) -> bool:
    return isinstance(u, str) and u.lower().startswith(("http://", "https://"))

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
    if not is_http(url): return None
    for attempt in range(RETRIES + 1):
        try:
            r = sess.get(url, timeout=TIMEOUT, allow_redirects=True)
            r.raise_for_status()
            r._content = r.content[:MAX_BYTES]   # trim
            return r
        except Exception:
            if attempt >= RETRIES:
                return None
            time.sleep(0.8 * (attempt + 1))
    return None

# ---------- HTML / JSON-LD helpers ----------
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

def first_mall_like(ldjson_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    # Many malls label as ShoppingCenter, LocalBusiness, Organization
    pref = {"shoppingcenter", "localbusiness", "organization", "place"}
    for obj in ldjson_list:
        t = obj.get("@type")
        if isinstance(t, list):
            tset = {str(x).lower() for x in t}
            if tset & pref: return obj
        else:
            if str(t).lower() in pref: return obj
        if "@graph" in obj:
            for node in obj["@graph"]:
                tt = str(node.get("@type","")).lower()
                if tt in pref: return node
    return None

def meta_desc(soup: BeautifulSoup) -> Optional[str]:
    for sel, key in (('meta[name="description"]', "content"),
                     ('meta[property="og:description"]', "content")):
        for tag in soup.select(sel):
            val = clean(tag.get(key))
            if val: return val
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

# ---------- Image filters / stock ----------
LOGO_PAT = re.compile(r"(?:^|/)(?:logo|logos?|brand|mark|icon|icons?|favicon|sprite|social)(?:[-_./]|$)", re.I)
SVG_OR_ICO_PAT = re.compile(r"\.(?:svg|ico)(?:$|\?)", re.I)
SOCIAL_PIXEL_PAT = re.compile(r"(?:facebook\.com/|/facebook\.png|/pixel\.gif|/analytics)", re.I)

def looks_like_logo_or_icon(url: str) -> bool:
    u = url or ""
    return bool(LOGO_PAT.search(u) or SVG_OR_ICO_PAT.search(u) or SOCIAL_PIXEL_PAT.search(u))

def acceptable_content_type(ct: Optional[str]) -> bool:
    if not ct: return False
    ct = ct.lower().strip()
    if not ct.startswith("image/"): return False
    if "svg" in ct: return False
    return True

def big_enough(bytes_len: Optional[int]) -> bool:
    try:
        return int(bytes_len or 0) >= 8000    # ~8KB minimum to avoid tiny icons
    except Exception:
        return False

def fetch_head_like(sess: requests.Session, url: str) -> Tuple[Optional[str], Optional[int]]:
    try:
        r = sess.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True)
        ct = r.headers.get("Content-Type")
        cl = r.headers.get("Content-Length")
        r.close()
        return (ct, int(cl) if cl and cl.isdigit() else None)
    except Exception:
        return (None, None)

# Swap to your local stock if preferred
MUSCAT_STOCK = [
    "https://www.omanobserver.om/omanobserver/uploads/images/2024/06/25/2701550.jpg",
    "https://www.omanobserver.om/omanobserver/uploads/images/2025/03/18/2958648.jpg",
    "https://www.omanobserver.om/omanobserver/uploads/images/2025/03/18/2958649.jpg",
    "https://www.omanobserver.om/omanobserver/uploads/images/2024/07/21/2723587.jpg",
    "https://www.omanobserver.om/omanobserver/uploads/images/2025/05/11/3009009.jpeg",
    "https://www.omanobserver.om/omanobserver/uploads/images/2025/04/02/2969730.jpeg",
]
def pick_muscat_stock(key: str = "") -> Optional[str]:
    if not MUSCAT_STOCK: return None
    h = int(hashlib.sha1((key or 'muscat').encode('utf-8')).hexdigest(), 16)
    return MUSCAT_STOCK[h % len(MUSCAT_STOCK)]

# ---------- Site hero detection ----------
def select_from_srcset(attr: str) -> Optional[str]:
    try:
        parts = [p.strip() for p in attr.split(",")]
        if not parts: return None
        return parts[-1].split()[0]
    except Exception:
        return None

def find_site_hero_url(sess: requests.Session, soup: BeautifulSoup, base_url: str) -> Optional[str]:
    metas: List[str] = []
    for name in ("property", "name"):
        for key in ("og:image", "twitter:image", "twitter:image:src"):
            for tag in soup.find_all("meta", {name: key}):
                val = clean(tag.get("content"))
                if val:
                    metas.append(absolute(base_url, html.unescape(val)))

    link_tag = soup.find("link", {"rel": "image_src"})
    if link_tag and link_tag.get("href"):
        metas.append(absolute(base_url, link_tag["href"].strip()))

    candidates: List[str] = []
    hero_words = ("hero", "banner", "header", "masthead", "slideshow", "carousel")
    for img in soup.find_all("img"):
        classes = " ".join(img.get("class") or []).lower()
        alt = (img.get("alt") or "").lower()
        attrs = " ".join([classes, alt])
        if any(w in attrs for w in hero_words):
            for key in ("data-src", "data-original", "data-lazy", "src", "data-url"):
                val = img.get(key)
                if val: candidates.append(val)
            if img.get("srcset"):
                ss = select_from_srcset(img["srcset"])
                if ss: candidates.append(ss)

    if not candidates:
        for img in soup.find_all("img"):
            for key in ("data-src", "data-original", "src"):
                val = img.get(key)
                if val:
                    candidates.append(val)
                    break
            if img.get("srcset"):
                ss = select_from_srcset(img["srcset"])
                if ss: candidates.append(ss)

    all_cands, seen = [], set()
    for href in [*metas, *candidates]:
        if not href: continue
        url = absolute(base_url, html.unescape(href.strip()))
        if not is_http(url): continue
        if url in seen: continue
        seen.add(url)
        all_cands.append(url)

    filtered = [u for u in all_cands if not looks_like_logo_or_icon(u)]

    for u in filtered:
        ct, size = fetch_head_like(sess, u)
        if acceptable_content_type(ct) and big_enough(size):
            return u
    for u in filtered:
        ct, _ = fetch_head_like(sess, u)
        if acceptable_content_type(ct):
            return u
    return None

# ---------- Mall-specific detectors ----------
DIR_WORDS   = ("directory", "store directory", "stores", "shop directory", "brands")
MAP_WORDS   = ("map", "mall map", "floor map", "wayfinding")
EVENT_WORDS = ("events", "what's on", "whats on", "happening")
OFFER_WORDS = ("offers", "promotions", "deals", "sale")
PARK_WORDS  = ("parking", "car park", "parking info", "valet")

AMENITY_WORD_SETS = {
    "parking": ("parking", "car park", "multi-storey parking"),
    "valet": ("valet", "valet parking"),
    "cinema": ("cinema", "movie", "theatre", "theater"),
    "food_court": ("food court", "dining court"),
    "supermarket": ("supermarket", "hypermarket", "grocery"),
    "pharmacy": ("pharmacy", "chemist", "drug store"),
    "kids_area": ("kids area", "play area", "family zone", "children play"),
    "prayer_room": ("prayer room", "masjid", "mosque"),
    "wheelchair_access": ("wheelchair", "accessible", "disabled access"),
    "atm": ("atm", "cash machine", "cashpoint"),
    "free_wifi": ("free wifi", "free wi-fi", "complimentary wifi", "wifi available"),
}

def find_first_link_containing(soup: BeautifulSoup, base: str, words: Tuple[str, ...]) -> Optional[str]:
    for a in soup.find_all("a", href=True):
        txt = clean(a.get_text(" ", strip=True)).lower()
        if any(w in txt for w in words):
            return absolute(base, a["href"])
    return None

# ---------- Wikipedia helpers ----------
def wikipedia_page_image(sess: requests.Session, name: str, city: str) -> Optional[str]:
    try:
        params = {
            "action": "query","format": "json","list": "search",
            "srsearch": f"{name} {city}".strip(),"srlimit": 1,"srprop": ""
        }
        r = sess.get("https://en.wikipedia.org/w/api.php", params=params, timeout=TIMEOUT)
        if not r.ok: return None
        hits = (r.json().get("query") or {}).get("search") or []
        if not hits: return None
        title = hits[0].get("title") or ""
        if not title: return None
        params2 = {
            "action": "query","format": "json","prop": "pageimages|pageprops",
            "piprop": "original","titles": title
        }
        r2 = sess.get("https://www.en.wikipedia.org/w/api.php", params=params2, timeout=TIMEOUT)
        if not r2.ok: return None
        pages = (r2.json().get("query") or {}).get("pages") or {}
        for _, page in pages.items():
            orig = (page.get("original") or {}).get("source")
            if is_http(orig) and not looks_like_logo_or_icon(orig):
                return orig
    except Exception:
        return None
    return None

# ---------- Icon finder ----------
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

# ---------- Enrichment per row ----------
def enrich_row(sess: requests.Session, row: Dict[str, str]) -> Dict[str, str]:
    site = clean(row.get("website") or row.get("url"))
    page_resp = fetch(sess, site) if is_http(site) else None
    soup = BeautifulSoup(page_resp.text, "html.parser") if page_resp else None
    ld = jsonld_blocks(soup) if soup else []
    mall_ld = first_mall_like(ld) if ld else None

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
                row["about_long"] = clamp_text(long_txt, 650)

    # JSON-LD: sometimes has description / amenityFeature / openingHours
    if mall_ld:
        if not clean(row.get("description")) and mall_ld.get("description"):
            row["description"] = clean(mall_ld.get("description"))
        if not clean(row.get("amenities")):
            amen = []
            af = mall_ld.get("amenityFeature")
            if isinstance(af, list):
                for it in af:
                    if isinstance(it, dict):
                        nm = clean(it.get("name"))
                        if nm: amen.append(nm)
            if amen:
                row["amenities"] = ";".join(dict.fromkeys(amen))

    # hero_url pipeline
    if not clean(row.get("hero_url")) and soup and page_resp is not None:
        site_hero = find_site_hero_url(sess, soup, page_resp.url)
        if is_http(site_hero) and not looks_like_logo_or_icon(site_hero):
            row["hero_url"] = site_hero
            row.setdefault("image_credit", "Official site")
            row.setdefault("image_source_url", page_resp.url)

    if not clean(row.get("hero_url")):
        wpi = wikipedia_page_image(sess, clean(row.get("name")), clean(row.get("city") or "Muscat"))
        if is_http(wpi) and not looks_like_logo_or_icon(wpi):
            row["hero_url"] = wpi
            row.setdefault("image_credit", "Wikipedia")
            row.setdefault("image_source_url", wpi)

    if not clean(row.get("hero_url")):
        stock = pick_muscat_stock(key=clean(row.get("slug") or row.get("name") or ""))
        if stock:
            row["hero_url"] = stock
            row.setdefault("image_credit", "Muscat stock")
            row.setdefault("image_source_url", stock)

    # Useful links + amenities
    if soup and page_resp is not None:
        base = page_resp.url
        txt = soup.get_text(" ", strip=True).lower()

        if not clean(row.get("directory_url")):
            du = find_first_link_containing(soup, base, DIR_WORDS)
            if is_http(du): row["directory_url"] = du

        if not clean(row.get("map_url")):
            mu = find_first_link_containing(soup, base, MAP_WORDS)
            if is_http(mu): row["map_url"] = mu

        if not clean(row.get("events_url")):
            eu = find_first_link_containing(soup, base, EVENT_WORDS)
            if is_http(eu): row["events_url"] = eu

        if not clean(row.get("offers_url")):
            ou = find_first_link_containing(soup, base, OFFER_WORDS)
            if is_http(ou): row["offers_url"] = ou

        if not clean(row.get("parking_info_url")):
            pu = find_first_link_containing(soup, base, PARK_WORDS)
            if is_http(pu): row["parking_info_url"] = pu

        # amenity flags
        for field, words in AMENITY_WORD_SETS.items():
            if not clean(row.get(field)) and any(w in txt for w in words):
                row[field] = "Yes"

        # Aggregate amenities string if empty
        if not clean(row.get("amenities")):
            am = []
            for key, label in [
                ("parking", "parking"),
                ("valet", "valet"),
                ("cinema", "cinema"),
                ("food_court", "food court"),
                ("supermarket", "supermarket"),
                ("pharmacy", "pharmacy"),
                ("kids_area", "kids area"),
                ("prayer_room", "prayer room"),
                ("wheelchair_access", "wheelchair access"),
                ("atm", "ATM"),
                ("free_wifi", "free wifi"),
            ]:
                if clean(row.get(key)) == "Yes":
                    am.append(label)
            if am:
                row["amenities"] = ";".join(am)

    return row

# ---------- CLI ----------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Enrich malls CSV (free sources only).")
    ap.add_argument("--csv", default="data/sources/malls.csv",
                    help="Path to malls CSV (will be updated in place).")
    ap.add_argument("--sleep", type=float, default=PAUSE,
                    help="Pause between rows (seconds).")
    ap.add_argument("--limit", type=int, default=0,
                    help="Optional: process only first N rows (for testing).")
    args = ap.parse_args()

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"CSV not found: {path}")

    # Load CSV; ensure fields exist even if your template lacks some
    with path.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        fieldnames = rdr.fieldnames or []
        must_have = [
            "logo_url","about_short","about_long","image_credit","image_source_url","hero_url",
            "directory_url","map_url","events_url","offers_url","parking_info_url",
            "parking","valet","cinema","food_court","supermarket","pharmacy",
            "kids_area","prayer_room","wheelchair_access","atm","free_wifi","amenities"
        ]
        rows: List[Dict[str, str]] = []
        for r in rdr:
            for k in must_have:
                r.setdefault(k, "")
            rows.append(r)

    # Enrich
    sess = session_with_retries()
    updated = 0
    n = len(rows) if args.limit <= 0 else min(len(rows), args.limit)
    for i in range(n):
        row = rows[i]
        try:
            new_row = enrich_row(sess, row)
            if new_row != row:
                rows[i] = new_row
                updated += 1
        except Exception:
            # keep going on errors
            pass
        time.sleep(args.sleep)

    # Write back (keep original columns order + any new fields)
    out_fields = list(rows[0].keys()) if rows else fieldnames
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Enrichment complete. Rows updated: {updated}/{n}")

if __name__ == "__main__":
    main()
