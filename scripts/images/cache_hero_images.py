#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv, os, sys, time, re
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image

# ---------- Paths ----------
ROOT = Path(__file__).resolve().parents[2]   # scripts/images/ under repo root
SRC_CSV = ROOT / "data" / "sources" / "hotels.csv"
ASSETS_DIR = ROOT / "assets" / "hotels"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR = ASSETS_DIR / "_tmp"
TMP_DIR.mkdir(exist_ok=True)

# ---------- Helpers ----------
def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"(^-|-$)", "", s)

def is_http(u: str) -> bool:
    try:
        return urlparse(u).scheme in ("http", "https")
    except Exception:
        return False

def http_get(url, timeout=30, max_retries=3, backoff=1.5, stream=False):
    attempt = 0
    while True:
        try:
            r = requests.get(url, timeout=timeout, allow_redirects=True, stream=stream)
            r.raise_for_status()
            return r
        except Exception:
            attempt += 1
            if attempt >= max_retries:
                raise
            time.sleep(backoff ** attempt)

def download_to(path: Path, url: str):
    r = http_get(url, timeout=60, stream=True)
    with path.open("wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 15):
            if chunk:
                f.write(chunk)
    return path

def ensure_rgb(img: Image.Image) -> Image.Image:
    # webp likes RGB; convert if needed
    if img.mode in ("RGB", "RGBA"):
        return img.convert("RGB")
    return img.convert("RGB")

def save_webp(src_path: Path, out_path: Path, target_w: int, quality=82):
    with Image.open(src_path) as im:
        im = ensure_rgb(im)
        w, h = im.size
        if w <= target_w:
            # do not upscale — save at original size but WebP
            im.save(out_path, "WEBP", quality=quality, method=6)
            return out_path
        new_h = int(h * (target_w / float(w)))
        im = im.resize((target_w, new_h), Image.LANCZOS)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        im.save(out_path, "WEBP", quality=quality, method=6)
        return out_path

# ---------- Main ----------
def main():
    if not SRC_CSV.exists():
        print(f"ERROR: {SRC_CSV} not found", file=sys.stderr)
        sys.exit(1)

    # read CSV
    rows = []
    with SRC_CSV.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        fieldnames = rdr.fieldnames or []
        for row in rdr:
            rows.append(row)

    updated = 0
    for row in rows:
        url = (row.get("hero_url") or "").strip()
        name = (row.get("name") or "").strip()
        slug = (row.get("slug") or slugify(name)) or "item"

        # only process online images; skip empty or already-local
        if not url or not is_http(url):
            continue

        base = ASSETS_DIR / slug  # base filename without extension
        orig_path = TMP_DIR / f"{slug}.orig"

        # If we’ve already created 1280.webp, skip downloading again
        webp_1280 = ASSETS_DIR / f"{slug}-1280.webp"
        webp_640  = ASSETS_DIR / f"{slug}-640.webp"
        if webp_1280.exists() and webp_640.exists():
            # point CSV to the local 1280.webp
            rel = webp_1280.relative_to(ROOT).as_posix()
            if row.get("hero_url") != rel:
                row["hero_url"] = rel
                updated += 1
            continue

        try:
            print(f"• caching {slug} …")
            download_to(orig_path, url)
            save_webp(orig_path, webp_1280, 1280)
            save_webp(orig_path, webp_640, 640)
        except Exception as e:
            print(f"  ! failed for {slug}: {e}", file=sys.stderr)
            continue
        finally:
            # keep tmp for a while; comment the next line to retain originals
            if orig_path.exists():
                try: orig_path.unlink()
                except: pass

        # update CSV to local 1280.webp
        rel = webp_1280.relative_to(ROOT).as_posix()
        row["hero_url"] = rel
        updated += 1

    # write back CSV (in-place)
    if rows:
        fieldnames = rows[0].keys()
    with SRC_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Done. Updated {updated} rows. Images at: {ASSETS_DIR}")

if __name__ == "__main__":
    main()
