#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV -> data/tools.json (+ logo download & optimize to assets/images/)
- Validates against data/schema/tools.schema.json (widened hours schema)
- Merges by slug (updates only the fields this pipeline owns)
"""

import csv, json, re, sys
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image, UnidentifiedImageError
from jsonschema import validate, exceptions as js_exceptions

# --- Paths ---------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "sources" / "places.csv"
TOOLS_JSON = ROOT / "data" / "tools.json"
CATEGORIES_JSON = ROOT / "data" / "categories.json"
SCHEMA_PATH = ROOT / "data" / "schema" / "tools.schema.json"
IMAGES_DIR = ROOT / "assets" / "images"
FALLBACK_LOGO = "assets/images/default.webp"

IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# --- Helpers -------------------------------------------------------
_slug_re = re.compile(r"[^a-z0-9]+")

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = _slug_re.sub("-", s).strip("-")
    return s or "item"

def split_tags(s: str):
    if not s:
        return []
    return [t.strip() for t in s.split(";") if t.strip()]

def load_json(p: Path, default):
    if not p.exists():
        return default
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(p: Path, obj):
    # pretty + stable ordering
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)

def safe_float(v):
    try:
        return float(v) if v not in (None, "",) else None
    except ValueError:
        return None

def file_ext_from_url(url: str) -> str:
    try:
        path = urlparse(url).path
        ext = Path(path).suffix.lower()
        return ext if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg") else ""
    except Exception:
        return ""

def download_logo(url: str, out_path: Path) -> str:
    """
    Download logo and convert to .webp (<= 512px max side).
    Returns repo-relative path string or FALLBACK_LOGO on failure.
    """
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()

        # Load image from bytes
        from io import BytesIO
        bio = BytesIO(r.content)

        # If it's SVG or non-raster, fall back (Pillow cannot rasterize SVG natively)
        ext = file_ext_from_url(url)
        if ext == ".svg":
            # keep the original file for reference but use fallback in UI
            (out_path.parent / (out_path.stem + ".svg")).write_bytes(r.content)
            return FALLBACK_LOGO

        img = Image.open(bio)
        # normalize mode
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")

        # Resize (max 512px)
        w, h = img.size
        max_dim = 512
        scale = min(1.0, max_dim / max(w, h)) if max(w, h) > 0 else 1.0
        if scale < 1:
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        out_path = out_path.with_suffix(".webp")
        img.save(out_path, "WEBP", method=6, quality=85)

        return str(out_path.relative_to(ROOT)).replace("\\", "/")
    except (requests.RequestException, UnidentifiedImageError, OSError) as e:
        print(f"[warn] logo download/convert failed for {url}: {e}", file=sys.stderr)
        return FALLBACK_LOGO

_hours_range_re = re.compile(r"([^0-9]+)\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})")

def parse_hours(hours_raw: str):
    """
    Returns:
      - list of {days, open, close} (new shape), or
      - None
    We *do not* attempt to write the legacy per-day object; if existing entries
    already have that shape, the schema accepts it and we leave them untouched.
    """
    if not hours_raw or not hours_raw.strip():
        return None
    parts = [p.strip() for p in hours_raw.split(";") if p.strip()]
    out = []
    for p in parts:
        m = _hours_range_re.match(p)
        if m:
            out.append({"days": m.group(1).strip(), "open": m.group(2), "close": m.group(3)})
        else:
            # fall back to raw bucket
            out.append({"days": p, "open": "", "close": ""})
    return out or None

# --- Main ----------------------------------------------------------
def main():
    # 1) Load categories (supports both flat array and {"categories":[...]})
    cat_data = load_json(CATEGORIES_JSON, [])
    if isinstance(cat_data, dict) and "categories" in cat_data:
        cat_list = cat_data.get("categories", [])
    else:
        cat_list = cat_data  # already a list

    # Build canonical map (lowercase keys) and a set of valid canonical names
    canonical = {}
    canonical_names = set()
    for c in cat_list or []:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip()
        if not name:
            continue
        canonical[name.lower()] = name
        canonical_names.add(name.lower())
        for syn in (c.get("synonyms") or []):
            syn_s = (str(syn) or "").strip()
            if syn_s:
                canonical[syn_s.lower()] = name

    # 2) Read existing tools.json (if any)
    tools = load_json(TOOLS_JSON, [])
    if not isinstance(tools, list):
        print(f"[error] {TOOLS_JSON} is not a JSON array; aborting.", file=sys.stderr)
        sys.exit(1)
    by_slug = {t.get("slug"): t for t in tools if isinstance(t, dict) and t.get("slug")}

    # 3) Read CSV
    if not CSV_PATH.exists():
        print(f"[error] CSV not found: {CSV_PATH}", file=sys.stderr)
        sys.exit(1)

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # i = CSV line number (after header)
            name = (row.get("name") or "").strip()
            if not name:
                print(f"[warn] skipping row {i}: empty name")
                continue

            slug = (row.get("slug") or "").strip() or slugify(name)

            # category (case-insensitive; validates only if categories.json provided)
            cat_in = (row.get("category") or "").strip()
            cat = canonical.get(cat_in.lower())
            if not cat:
                if canonical_names:
                    raise ValueError(
                        f"Unknown category '{cat_in}' for '{name}' at CSV line {i}. "
                        f"Add/match it in data/categories.json."
                    )
                else:
                    cat = cat_in  # no configured list to validate against

            # tags
            tags = split_tags(row.get("tags") or "")

            # logo resolution
            logo_path_csv = (row.get("logo_path") or "").strip()
            logo_url = (row.get("logo_url") or "").strip()
            if logo_path_csv:
                # trust the given repo path
                logo_repo_path = logo_path_csv
            elif logo_url:
                # download and convert to webp
                out = IMAGES_DIR / f"{slug}"
                logo_repo_path = download_logo(logo_url, out)
            else:
                logo_repo_path = FALLBACK_LOGO

            # location
            location = {
                "neighborhood": (row.get("neighborhood") or "").strip() or None,
                "address": (row.get("address") or "").strip() or None,
                "city": (row.get("city") or "").strip() or None,
                "country": (row.get("country") or "").strip() or None,
            }
            lat = safe_float(row.get("lat"))
            lng = safe_float(row.get("lng"))
            if lat is not None:
                location["lat"] = lat
            if lng is not None:
                location["lng"] = lng
            location = {k: v for k, v in location.items() if v not in (None, "",)}

            # hours (new shape array or None)
            hours = parse_hours(row.get("hours_raw") or "")

            # minimal object per your schema
            obj = {
                "id": (row.get("id") or slug),
                "slug": slug,
                "name": name,
                "categories": [cat],
                "tagline": (row.get("tagline") or "").strip(),
                "tags": tags,
                "logo": logo_repo_path,
                "location": location,
                "hours": hours,
                "url": (row.get("url") or "").strip(),  # optional
            }

            if slug in by_slug and by_slug[slug] is not None:
                # merge: update only the keys we own; keep your custom fields intact
                existing = by_slug[slug]
                for k, v in obj.items():
                    if v not in (None, "", [], {}):
                        existing[k] = v
            else:
                tools.append(obj)
                by_slug[slug] = obj

    # 4) Sort for stable diffs
    tools.sort(key=lambda t: (t.get("name") or "").lower())

    # 5) Validate with JSON Schema
    schema = load_json(SCHEMA_PATH, None)
    if schema:
        try:
            validate(instance=tools, schema=schema)
        except js_exceptions.ValidationError as e:
            # Surface a helpful message in CI logs
            print("[error] tools.json failed schema validation:", file=sys.stderr)
            print(e.message, file=sys.stderr)
            # Show roughly where
            print(f"path: {'/'.join(map(str, e.path))}", file=sys.stderr)
            sys.exit(1)

    # 6) Write result
    save_json(TOOLS_JSON, tools)
    print(f"[ok] wrote {TOOLS_JSON} with {len(tools)} records.")

if __name__ == "__main__":
    main()
