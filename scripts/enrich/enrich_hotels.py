#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enrich hotels CSV with free web signals (no Google paid APIs).

Fills empty fields only:
- logo_url, about_short, about_long, price_range, star_rating,
  checkin_time, checkout_time, hotel_amenities, amenities,
  hero_url, image_credit, image_source_url, wikidata_id, distance_to_airport,
  breakfast_included, parking

Input CSV must have columns observed in your current file:
['id','slug','name','category','tagline','tags','neighborhood','address','city','country',
 'lat','lng','website','phone','maps_url','hours_raw','logo_url','hero_url','image_credit',
 'image_source_url','place_id','osm_type','osm_id','wikidata_id','url','description',
 'price_range','about_short','about_long','amenities','rating_overall','sub_service',
 'sub_ambience','sub_value','sub_accessibility','review_count','review_source',
 'review_insight','last_updated','star_rating','checkin_time','checkout_time','room_types',
 'hotel_amenities','booking_url','distance_to_airport','breakfast_included','parking']
"""

from __future__ import annotations
import csv, re, time, json, math
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
from bs4 import BeautifulSoup

# ----- Config -----
HEADERS = {
    "User-Agent": "BestMuscatBot/1.0 (+https://bestmuscat.com/; admin@bestmuscat.com)"
}
TIMEOUT = 20
PAUSE = 0.8   # be polite between domains
RETRIES = 2   # lightweight retry for flaky sites

# Muscat International Airport (MCT)
MCT_LAT, MCT_LNG = 23.5933, 58.2844

# Meta image selectors for site hero discovery
META_OG_TW = [
    ('meta[property="og:image"]', "content"),
    ('meta[name="og:image"]', "content"),
    ('meta[name="twitter:image"]', "content"),
    ('meta[property="twitter:image"]', "content"),
]

# ----- Helpers -----
def is_http(u: Optional[str]) -> bool:
    return isinstance(u, str) and u.lower().startswith(("http://", "https://"))

def clean(s: Any) -> str:
    return (s or "").strip()

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
            # Cap the body size we’ll parse to avoid huge pages
            r._content = r.content[:350_000]
            return r
        except Exception:
            if attempt >= RETRIES:
                return None
            time.sleep(0.6 * (attempt + 1))
    return None

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

def find_icons(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    # Try common icon rels; prefer the first valid absolute URL
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
    # Fallback to /favicon.ico
    root = domain_root(base_url)
    if root:
        return root.rstrip("/") + "/favicon.ico"
    return None

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
                if tt.lower() in {"hotel", "lodgingbusiness"}:
                    return node
        if t.lower() in {"hotel", "lodgingbusiness"}:
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

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0088
    from math import radians, sin, cos, asin, sqrt
    dlat = radians(lat2 - lat1)
    dlon = radians(lat2 - lon1)
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

def wikidata_main_image(sess: requests.Session, qid: str) -> Optional[str]:
    """Return a Wikimedia 'Special:FilePath/...' URL for the entity's main image (P18)."""
    if not qid:
        return None
    try:
        r = sess.get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json", timeout=TIMEOUT)
        r.raise_for_status()
        ent = next(iter(r.json().get("entities", {}).values()))
        claims = ent.get("claims", {})
        if "P18" in claims:
            file_name = claims["P18"][0]["mainsnak"]["datavalue"]["value"]
            return f"https://commons.wikimedia.org/wiki/Special:FilePath/{file_name.replace(' ', '_')}"
    except Exception:
        return None
    return None

def site_hero_from_meta(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    for sel, attr in META_OG_TW:
        for tag in soup.select(sel):
            val = clean(tag.get(attr))
            if val:
                return absolute(base_url, val)
    return None

# ----- Main enrichment per row -----
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

    # logo_url (favicon or icon link)
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
        # price_range
        if not clean(row.get("price_range")) and hotel_ld.get("priceRange"):
            row["price_range"] = clean(hotel_ld.get("priceRange"))
        # star_rating
        if not clean(row.get("star_rating")):
            sr = hotel_ld.get("starRating") or {}
            if isinstance(sr, dict):
                val = sr.get("ratingValue") or sr.get("rating")
                if val:
                    row["star_rating"] = str(val).strip()
        # checkin/checkout
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
        amen = list(dict.fromkeys(amen))  # unique preserve order
        # text-based amenities
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
            if ("breakfast included" in txt or
                "free breakfast" in txt or
                "complimentary breakfast" in txt):
                row["breakfast_included"] = "Yes"
        if not clean(row.get("parking")):
            if ("free parking" in txt or
                "parking available" in txt or
                "valet parking" in txt):
                row["parking"] = "Yes"

    # --- HERO URL (free) ---
    if not clean(row.get("hero_url")):
        # 1) Try site OG/Twitter image
        if soup and page_resp is not None:
            hero_meta = site_hero_from_meta(soup, page_resp.url)
            if is_http(hero_meta):
                row["hero_url"] = hero_meta
                # Set source/credit right away for site-based images
                if not clean(row.get("image_credit")):
                    row["image_credit"] = "Official site"
                if not clean(row.get("image_source_url")):
                    row["image_source_url"] = page_resp.url

    if not clean(row.get("hero_url")) and name:
        # 2) Try Wikidata main image (P18)
        qid = clean(row.get("wikidata_id")) or wikidata_qid(sess, name, city)
        if qid:
            hero_wd = wikidata_main_image(sess, qid)
            if is_http(hero_wd):
                row["hero_url"] = hero_wd
                if not clean(row.get("wikidata_id")):
                    row["wikidata_id"] = qid
                if not clean(row.get("image_credit")):
                    row["image_credit"] = "Wikimedia Commons"
                if not clean(row.get("image_source_url")):
                    row["image_source_url"] = hero_wd

    # image_credit/source normalization if hero already present
    hero = clean(row.get("hero_url"))
    if is_http(hero):
        if ("wikimedia.org" in hero) or ("commons.wikimedia.org" in hero):
            if not clean(row.get("image_credit")):
                row["image_credit"] = "Wikimedia Commons"
            if not clean(row.get("image_source_url")):
                row["image_source_url"] = hero
        else:
            if not clean(row.get("image_credit")):
                row["image_credit"] = "Official site"
            if not clean(row.get("image_source_url")) and page_resp is not None:
                row["image_source_url"] = page_resp.url

    # wikidata_id (if still missing and we haven't looked it up yet)
    if not clean(row.get("wikidata_id")) and name:
        qid = wikidata_qid(sess, name, city)
        if qid:
            row["wikidata_id"] = qid

    # distance_to_airport
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
            "hero_url","image_credit","image_source_url","wikidata_id",
            "distance_to_airport","breakfast_included","parking"
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
