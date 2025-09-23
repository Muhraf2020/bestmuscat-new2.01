# FILE: scripts/fetch_logos.py
"""
Fetch per-tool logos and update data/tools.json with local logo paths.

Strategy per tool (when logo is missing or "generic.png"):
1) Try Clearbit logo:   https://logo.clearbit.com/<domain>?size=256&format=png
2) Try Google favicon:  https://www.google.com/s2/favicons?domain=<domain>&sz=128
3) Parse the homepage HTML for:
   - <link rel="icon" ...> / apple-touch-icon / mask-icon
   - <meta property="og:image" ...> / <meta name="twitter:image" ...>
The first image we can successfully fetch becomes the logo.

We save logos to assets/logos/<slug>.png and write that path back into tools.json.
"""

import json
import os
import re
import sys
import time
from io import BytesIO
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(__file__))  # repo root from scripts/
DATA_JSON = os.path.join(ROOT, "data", "tools.json")
LOGO_DIR = os.path.join(ROOT, "assets", "logos")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LogoFetcher/1.0; +https://github.com/)"
}
TIMEOUT = 15


def slugify(s: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", s.lower()))[:128]


def ensure_dirs():
    os.makedirs(LOGO_DIR, exist_ok=True)


def is_image_response(resp: requests.Response) -> bool:
    ct = resp.headers.get("Content-Type", "").lower()
    return resp.status_code == 200 and ("image/" in ct or resp.content[:4] in [b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1"])


def download_image(url: str) -> Image.Image | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if not is_image_response(r):
            return None
        im = Image.open(BytesIO(r.content))
        # Convert to RGBA to preserve transparency, then later save as PNG
        return im.convert("RGBA")
    except Exception:
        return None


def save_png(im: Image.Image, path: str):
    # If very small (e.g., 16px favicon), upscale a bit for nicer display
    w, h = im.size
    if max(w, h) < 64:
        scale = 128 // max(1, max(w, h))
        if scale > 1:
            im = im.resize((max(64, w * scale), max(64, h * scale)), Image.LANCZOS)
    im.save(path, format="PNG", optimize=True)


def domain_from_url(url: str) -> str:
    try:
        netloc = urlparse(url).netloc
        return netloc.split("@")[-1]
    except Exception:
        return ""


def homepage_icons(home_url: str) -> list[str]:
    """Scrape a homepage for candidate icon/image URLs (absolute)."""
    try:
        r = requests.get(home_url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "lxml")

    candidates = []

    # <link rel="icon">, <link rel="shortcut icon">, apple-touch-icon, mask-icon, etc.
    for link in soup.find_all("link"):
        rel = (link.get("rel") or [])
        rel = [x.lower() for x in rel]
        if any(x in rel for x in ["icon", "shortcut icon", "apple-touch-icon", "apple-touch-icon-precomposed", "mask-icon"]):
            href = link.get("href")
            if href:
                candidates.append(urljoin(home_url, href))

    # Open Graph / Twitter
    for meta_name in [
        ("property", "og:image"),
        ("name", "og:image"),
        ("name", "twitter:image"),
        ("property", "twitter:image"),
    ]:
        meta = soup.find("meta", attrs={meta_name[0]: meta_name[1]})
        if meta and meta.get("content"):
            candidates.append(urljoin(home_url, meta["content"]))

    # De-dupe, preserve order
    seen = set()
    out = []
    for u in candidates:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def best_logo_for(url: str) -> Image.Image | None:
    dom = domain_from_url(url)
    if not dom:
        return None

    # 1) Clearbit
    clearbit = f"https://logo.clearbit.com/{dom}?size=256&format=png"
    im = download_image(clearbit)
    if im:
        return im

    # 2) Google favicon (png)
    google_fav = f"https://www.google.com/s2/favicons?domain={dom}&sz=128"
    im = download_image(google_fav)
    if im:
        return im

    # 3) Parse homepage for icons / OG images
    # Normalize homepage to scheme+domain only, but if path present, use as is.
    parsed = urlparse(url)
    home = f"{parsed.scheme}://{parsed.netloc}/"
    for candidate in homepage_icons(home):
        im = download_image(candidate)
        if im:
            return im

    return None


def main():
    ensure_dirs()

    with open(DATA_JSON, "r", encoding="utf-8") as f:
        tools = json.load(f)
        if not isinstance(tools, list):
            print("ERROR: data/tools.json must be an array of tools.")
            sys.exit(1)

    updated = 0
    skipped = 0

    for t in tools:
        name = t.get("name") or t.get("id") or "tool"
        slug = (t.get("slug") or slugify(name))
        url = t.get("url") or ""
        logo = t.get("logo") or ""

        # Only fetch when (a) we have a URL and (b) logo is missing or generic
        needs_logo = (not logo) or logo.endswith("/generic.png") or logo.endswith("generic.png")

        if not url or not needs_logo:
            skipped += 1
            continue

        print(f"[logo] Fetching for: {name}  ({url})")
        im = best_logo_for(url)
        if not im:
            print("  - No logo found. Leaving as is.")
            continue

        out_rel = f"assets/logos/{slug}.png"
        out_abs = os.path.join(ROOT, out_rel)
        save_png(im, out_abs)

        t["logo"] = out_rel
        updated += 1

        # Be nice to endpoints
        time.sleep(0.3)

    if updated:
        # Write back pretty but compact
        with open(DATA_JSON, "w", encoding="utf-8") as f:
            json.dump(tools, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"Updated {updated} logo(s).")
    else:
        print("No logos updated (either all set or no matches).")

    print(f"Skipped: {skipped}")


if __name__ == "__main__":
    main()
