#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enrich hotels CSV with free web signals (no Google paid APIs).

Fills empty fields only:
- logo_url, about_short, about_long, price_range, star_rating,
  checkin_time, checkout_time, hotel_amenities, amenities,
  hero_url, image_credit, image_source_url, wikidata_id,
  distance_to_airport, breakfast_included, parking
"""

from __future__ import annotations
import csv, re, time, json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import requests
from bs4 import BeautifulSoup

# ----- Config -----
HEADERS = {
    "User-Agent": "BestMuscatBot/1.0 (+https://bestmuscat.com/; admin@bestmuscat.com)",
    "Accept-Language": "en;q=1.0",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}
TIMEOUT = 25
PAUSE = 0.8
RETRIES = 2  # lightweight retry for flaky sites

# Muscat International Airport (MCT)
MCT_LAT, MCT_LNG = 23.5933, 58.2844

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
            # cap body size we parse (avoid giant pages)
            r._content = r.content[:500_000]
            return r
        except Exception:
            if attempt >= RETRIES:
                return None
            time.sleep(0.8 * (attempt + 1))
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

def looks_tiny_or_icon(url: str) -> bool:
    u = url.lower()
    if any(x in u for x in ("/favicon", "sprite", ".svg")):
        return True
    # quick heuristics for tiny sizes in query/paths
    if re.search(r"[\?&](w|width|h|height)=([0-9]{1,3})\b", u):
        m = re.search(r"[\?&](w|width|h|height)=([0-9]{1,3})\b", u)
        try:
            if int(m.group(2)) < 128:
                return True
        except Exception:
            pass
    return False

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
    for obj in ldjson_list:
        t = clean(obj.get("@type"))
        if not t and "@graph" in obj:
            for node in obj["@graph"]:
                tt = clean(node.get("@type"))
                if tt.lower() in {"hotel", "lodgingbusiness"}:
                    return node
        if t.lower() in {"hotel", "lodgingbusiness"}:
            return obj
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
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2) ** 2
    return round(2 * R * asin(sqrt(a)), 2)

# ---------- Image helpers (NEW) ----------
def _normalize_image_field(val: Any) -> Optional[str]:
    """
    Accepts JSON-LD image shapes: str | dict{"url": ...} | list[...]
    Returns first URL-like string or None.
    """
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        u = val.get("url") or val.get("@id") or val.get("contentUrl")
        return u if isinstance(u, str) else None
    if isinstance(val, list):
        for it in val:
            u = _normalize_image_field(it)
            if u:
                return u
    return None

def hero_from_jsonld_image(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    for block in jsonld_blocks(soup):
        for k in ("image", "logo"):
            if k in block:
                u = _normalize_image_field(block.get(k))
                if u:
                    absu = absolute(base_url, u)
                    if is_http(absu) and not looks_tiny_or_icon(absu):
                        return absu
    return None

def hero_from_meta_tags(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    cands = []
    for sel in [
        ('meta[property="og:image"]', "content"),
        ('meta[name="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
        ('meta[name="twitter:image:src"]', "content"),
        ('link[rel="image_src"]', "href"),
        ('meta[itemprop="image"]', "content"),
    ]:
        for tag in soup.select(sel[0]):
            val = clean(tag.get(sel[1]))
            if val:
                cands.append(val)
    for u in cands:
        absu = absolute(base_url, u)
        if is_http(absu) and not looks_tiny_or_icon(absu):
            return absu
    return None

def hero_from_largest_img(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """
    Fallback: choose the <img> with largest declared width/height attributes.
    """
    best: Tuple[int, str] | None = None
    for img in soup.find_all("img"):
        src = clean(img.get("src") or img.get("data-src") or "")
        if not src:
            continue
        absu = absolute(base_url, src)
        if not is_http(absu) or looks_tiny_or_icon(absu):
            continue
        w = img.get("width"); h = img.get("height")
        score = 0
        try:
            if w and str(w).isdigit(): score += int(w)
            if h and str(h).isdigit(): score += int(h)
        except Exception:
            pass
        # prefer images from same domain or CDN-ish paths
        if "logo" in absu.lower():  # skip logos for hero
            continue
        if not best or score > best[0]:
            best = (score, absu)
    return best[1] if best else None

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

def wikipedia_lead_image(sess: requests.Session, name: str, city: str) -> Optional[Tuple[str, str]]:
    """
    Returns (image_url, page_url) using Wikipedia API if a page exists.
    """
    q = f"{name} {city}".strip()
    try:
        # 1) Search
        s = sess.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": q,
                "format": "json",
                "srlimit": 1,
            },
            timeout=TIMEOUT,
        )
        if not s.ok:
            return None
        js = s.json()
        hits = (js.get("query") or {}).get("search") or []
        if not hits:
            return None
        title = hits[0].get("title")
        if not title:
            return None
        # 2) Get original image for the page
        p = sess.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": title,
                "prop": "pageimages|info",
                "piprop": "original",
                "inprop": "url",
                "format": "json",
            },
            timeout=TIMEOUT,
        )
        if not p.ok:
            return None
        pj = p.json()
        pages = (pj.get("query") or {}).get("pages") or {}
        for _, v in pages.items():
            orig = v.get("original", {})
            if "source" in orig:
                return orig["source"], v.get("fullurl") or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
    except Exception:
        return None
    return None

# ----- Enrichment per row -----
def enrich_row(sess: requests.Session, row: Dict[str, str]) -> Dict[str, str]:
    name = clean(row.get("name"))
    city = clean(row.get("city"))
    lat  = row.get("lat"); lng = row.get("lng")
    latf = float(lat) if lat not in (None, "",) else None
    lngf = float(lng) if lng not in (None, "",) else None

    site = clean(row.get("website") or row.get("url"))
    page_resp = fetch(sess, site) if is_http(site) else None
    soup = BeautifulSoup(page_resp.text, "html.parser") if page_resp else None
    ld = jsonld_blocks(soup) if soup else []
    hotel_ld = first_hotel_like(ld) if ld else None

    # logo_url
    if not clean(row.get("logo_url")) and soup:
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
        # amenity features + text mining
        amen = []
        af = hotel_ld.get("amenityFeature")
        if isinstance(af, list):
            for it in af:
                if isinstance(it, dict):
                    nm = clean(it.get("name"))
                    if nm:
                        amen.append(nm)
        page_text = soup.get_text(" ", strip=True) if soup else ""
        amen_k = extract_amenities_from_text(page_text)
        amen_all = ";".join(sorted(set([*amen, *amen_k]))) if (amen or amen_k) else ""
        if amen_all:
            if not clean(row.get("hotel_amenities")):
                row["hotel_amenities"] = amen_all
            if not clean(row.get("amenities")):
                row["amenities"] = amen_all

    # star via text
    if not clean(row.get("star_rating")) and soup:
        sr_txt = detect_star_from_text(soup.get_text(" ", strip=True))
        if sr_txt:
            row["star_rating"] = sr_txt

    # breakfast/parking heuristics
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

    # ---- HERO IMAGE (multi-source) ----
    if not clean(row.get("hero_url")):
        hero_url = None
        credit = None
        credit_link = None

        if soup:
            # 1) JSON-LD image/logo
            hero_url = hero_from_jsonld_image(soup, page_resp.url)
            # 2) OG/Twitter/link meta
            if not hero_url:
                hero_url = hero_from_meta_tags(soup, page_resp.url)
            # 3) Largest <img> declared
            if not hero_url:
                hero_url = hero_from_largest_img(soup, page_resp.url)
            if hero_url:
                credit = "Official site"
                credit_link = page_resp.url

        # 4) Wikipedia fallback (lead image)
        if not hero_url and name:
            wik_img = wikipedia_lead_image(sess, name, city)
            if wik_img:
                hero_url, page_url = wik_img
                credit = "Wikipedia"
                credit_link = page_url

        # 5) If we still have nothing, try Wikidata by name (may lead to Commons)
        if not hero_url and not clean(row.get("wikidata_id")) and name:
            qid = wikidata_qid(sess, name, city)
            if qid:
                row["wikidata_id"] = qid  # persist for future runs
        # (We’re not downloading/deriving Commons file here to keep it pure-URL and simple.)

        if hero_url and not looks_tiny_or_icon(hero_url):
            row["hero_url"] = hero_url
            if not clean(row.get("image_credit")) and credit:
                row["image_credit"] = credit
            if not clean(row.get("image_source_url")) and credit_link:
                row["image_source_url"] = credit_link

    # wikidata_id (if still missing and we didn’t set it above)
    if not clean(row.get("wikidata_id")) and name:
        qid = wikidata_qid(sess, name, city)
        if qid:
            row["wikidata_id"] = qid

    # distance_to_airport
    try:
        latf = float(row.get("lat") or "")
        lngf = float(row.get("lng
