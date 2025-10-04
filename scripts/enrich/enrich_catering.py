#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enrich catering CSV with free web signals (no paid APIs).

It:
- Finds hero_url from official site (og:image, twitter:image, hero-ish <img>), rejecting logos/pixels
- Falls back to Wikipedia page image (free) if site image missing
- Final fallback: curated Muscat stock image list (swap to local assets if you prefer)
- Extracts about_short / about_long from meta/first paragraph
- Detects favicon for logo_url when missing
- Detects useful links: sample menu / packages, inquiry / booking forms
- Heuristically flags service types & features:
  corporate, wedding, private events, live stations, buffet, delivery/setup,
  cuisines (Indian/Arabic/Italian/Asian/Middle Eastern/International), service area text
- Tries to extract simple price hints:
  min order (currency/amount) and per-person min/max if found in page text
- Aggregates a simple semicolon-separated `amenities` string from detected flags
- DOES NOT download images; only lightweight HEAD/GET checks

Run:
  python scripts/enrich/enrich_catering.py --csv data/sources/catering.csv
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

# ---------- Link & feature detectors (catering) ----------
MENU_WORDS = ("menu", "catering menu", "sample menu", "our menu", "set menu")
PACKAGE_WORDS = ("packages", "catering packages", "banquet packages", "party packages")
INQUIRY_WORDS = ("inquiry", "enquiry", "request a quote", "quote", "contact us", "book now", "booking", "order now")

SERVICE_TYPES = {
    "corporate_catering": ("corporate", "office", "business lunch", "boardroom"),
    "wedding_catering": ("wedding", "reception", "nikah"),
    "private_events": ("private event", "birthday", "house party", "family gathering"),
    "live_stations": ("live station", "live cooking", "action station"),
    "buffet": ("buffet", "banquet"),
    "delivery_available": ("delivery", "home delivery", "doorstep"),
    "setup_included": ("setup", "set-up", "tables and chairs", "chafing dish", "cutlery", "service staff"),
}

CUISINES = {
    "Indian": ("indian", "biryani", "tandoori", "masala"),
    "Arabic": ("arabic", "mezze", "shawarma", "mansaf", "kabsa"),
    "Middle Eastern": ("middle eastern", "levant", "mezze"),
    "Italian": ("italian", "pasta", "pizza", "risotto"),
    "Asian": ("asian", "thai", "sushi", "noodles", "dim sum"),
    "International": ("international", "global cuisine"),
    "Omani": ("omani", "shuwa", "mishkak"),
}

SERVICE_AREA_WORDS = ("service area", "we cover", "areas we serve", "deliver to", "available in")

CURRENCY = r"(OMR|USD|AED|€|\$|ر\.ع\.|رع)"
NUM = r"(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?"

# Examples: "OMR 150 minimum order", "min order OMR 100", "Minimum spend $500"
MIN_ORDER_PAT = re.compile(
    rf"(minimum(?:\s*order|\s*spend)?|min(?:\.|imum)?(?:\s*order|\s*spend)?)"
    rf".{{0,30}}({CURRENCY}).{{0,10}}({NUM})",
    re.I | re.S,
)

# Examples: "from OMR 4 per head", "OMR 3.5 per person", "AED 40 pp"
PER_PERSON_PAT = re.compile(
    rf"({CURRENCY}).{{0,3}}({NUM}).{{0,10}}(per\s*(?:person|head|guest)|pp)",
    re.I,
)

def find_first_link_containing(soup: BeautifulSoup, base: str, words: Tuple[str, ...]) -> Optional[str]:
    for a in soup.find_all("a", href=True):
        txt = clean(a.get_text(" ", strip=True)).lower()
        if any(w in txt for w in words):
            return absolute(base, a["href"])
    # also look for direct file links with menu/packages in name
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if (("menu" in href or "package" in href) and href.endswith((".pdf", ".jpg", ".jpeg", ".png"))):
            return absolute(base, a["href"])
    return None

def detect_service_types(text: str) -> Dict[str, str]:
    lt = text.lower()
    out = {}
    for field, cues in SERVICE_TYPES.items():
        out[field] = "Yes" if any(c in lt for c in cues) else ""
    return out

def detect_cuisines(text: str) -> str:
    lt = text.lower()
    hits = []
    for label, cues in CUISINES.items():
        if any(c in lt for c in cues):
            hits.append(label)
    return ";".join(sorted(set(hits)))

def extract_service_area(text: str) -> str:
    lt = text.lower()
    for w in SERVICE_AREA_WORDS:
        i = lt.find(w)
        if i != -1:
            snippet = text[max(0, i-40): i+120]
            return " ".join(snippet.split())
    return ""

def extract_min_order(text: str) -> Tuple[str, str]:
    m = MIN_ORDER_PAT.search(text)
    if not m: return ("", "")
    cur, amt = m.group(2), m.group(3)
    return (cur, amt.replace(",", ""))

def extract_per_person(text: str) -> Tuple[str, str, str]:
    # Collect all hits and summarize min/max amounts with a single currency if consistent
    hits: List[Tuple[str, float]] = []
    for m in PER_PERSON_PAT.finditer(text):
        cur = m.group(1)
        amt = m.group(2)
        try:
            hits.append((cur, float(amt.replace(",", ""))))
        except Exception:
            pass
    if not hits:
        return ("", "", "")
    # Prefer dominant currency among hits
    from collections import Counter
    cur = Counter([h[0] for h in hits]).most_common(1)[0][0]
    amts = [h[1] for h in hits if h[0] == cur]
    if not amts:
        return ("", "", "")
    lo, hi = min(amts), max(amts)
    # Avoid decimals in CSV unless needed
    def fmt(x: float) -> str:
        return str(int(x)) if abs(x - int(x)) < 1e-6 else f"{x:.2f}"
    return (cur, fmt(lo), fmt(hi))

# ---------- Wikipedia fallback ----------
def wikipedia_page_image(sess: requests.Session, name: str, city: str) -> Optional[str]:
    try:
        params = {"action": "query","format": "json","list": "search",
                  "srsearch": f"{name} {city}".strip(),"srlimit": 1,"srprop": ""}
        r = sess.get("https://en.wikipedia.org/w/api.php", params=params, timeout=TIMEOUT)
        if not r.ok: return None
        hits = (r.json().get("query") or {}).get("search") or []
        if not hits: return None
        title = hits[0].get("title") or ""
        if not title: return None
        params2 = {"action": "query","format": "json","prop": "pageimages|pageprops",
                   "piprop": "original","titles": title}
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

# ---------- Icons ----------
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

    # Links + features from page text
    if soup and page_resp is not None:
        base = page_resp.url
        txt = soup.get_text(" ", strip=True)

        # Useful links
        if not clean(row.get("menu_url")):
            mu = find_first_link_containing(soup, base, MENU_WORDS)
            if is_http(mu): row["menu_url"] = mu

        if not clean(row.get("packages_url")):
            pu = find_first_link_containing(soup, base, PACKAGE_WORDS)
            if is_http(pu): row["packages_url"] = pu

        if not clean(row.get("inquiry_url")):
            iu = find_first_link_containing(soup, base, INQUIRY_WORDS)
            if is_http(iu): row["inquiry_url"] = iu

        # Service types & features
        flags = detect_service_types(txt)
        for k, v in flags.items():
            if not clean(row.get(k)) and v:
                row[k] = v

        # Cuisines
        if not clean(row.get("cuisines")):
            cs = detect_cuisines(txt)
            if cs: row["cuisines"] = cs

        # Service area (best-effort snippet)
        if not clean(row.get("service_area")):
            sa = extract_service_area(txt)
            if sa: row["service_area"] = sa

        # Prices
        if not (clean(row.get("min_order_currency")) and clean(row.get("min_order_amount"))):
            cur, amt = extract_min_order(txt)
            if cur: row["min_order_currency"] = cur
            if amt: row["min_order_amount"] = amt

        if not (clean(row.get("per_person_min")) and clean(row.get("per_person_max"))):
            cur2, lo, hi = extract_per_person(txt)
            # If currency is absent but min_order_currency exists, we can skip setting currency for pp-range
            if lo and not clean(row.get("per_person_min")): row["per_person_min"] = lo
            if hi and not clean(row.get("per_person_max")): row["per_person_max"] = hi
            if cur2 and not clean(row.get("per_person_currency")): row["per_person_currency"] = cur2

        # Aggregate amenities from detected flags if `amenities` empty
        if not clean(row.get("amenities")):
            am = []
            for key, label in [
                ("delivery_available", "delivery"),
                ("setup_included", "setup included"),
                ("live_stations", "live stations"),
                ("buffet", "buffet"),
                ("corporate_catering", "corporate"),
                ("wedding_catering", "wedding"),
                ("private_events", "private events"),
            ]:
                if clean(row.get(key)) == "Yes":
                    am.append(label)
            if am:
                row["amenities"] = ";".join(am)

    return row

# ---------- CLI ----------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Enrich catering CSV (free sources only).")
    ap.add_argument("--csv", default="data/sources/catering.csv",
                    help="Path to catering CSV (will be updated in place).")
    ap.add_argument("--sleep", type=float, default=PAUSE,
                    help="Pause between rows (seconds).")
    ap.add_argument("--limit", type=int, default=0,
                    help="Optional: process only first N rows (for testing).")
    args = ap.parse_args()

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"CSV not found: {path}")

    # Load CSV; ensure fields exist even if template lacks some
    with path.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        fieldnames = rdr.fieldnames or []
        must_have = [
            "logo_url","about_short","about_long","image_credit","image_source_url","hero_url",
            "menu_url","packages_url","inquiry_url",
            "corporate_catering","wedding_catering","private_events",
            "live_stations","buffet","delivery_available","setup_included",
            "cuisines","service_area",
            "min_order_currency","min_order_amount",
            "per_person_currency","per_person_min","per_person_max",
            "amenities"
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
            # swallow & continue
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
