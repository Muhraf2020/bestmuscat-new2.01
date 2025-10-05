#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build assets/best-things.json from data/homepage/best_things.csv

- Filters to status=live and within the start/end date window
- Enforces category ∈ {"Tours & Experiences","Events and Venues","Wellness & Aesthetics"}
- Validates that url and image_url are http/https
- Appends UTM params when present (utm_source, utm_medium, utm_campaign)
- Sorts by priority (asc), then title
- Optional: cap items per category via --cap-per-cat (default 12)
- Supports optional UI fields: rating (float) and is_open (bool)
- Outputs compact, frontend-friendly JSON

Run:
  python scripts/ingest/best_things_from_csv.py
  # or with options:
  python scripts/ingest/best_things_from_csv.py --cap-per-cat 9
"""

from __future__ import annotations
import csv, json, sys, argparse, re
from pathlib import Path
from datetime import date
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

# ---- Paths (defaults; can be overridden by CLI) ----
DEFAULT_SRC = Path("data/homepage/best_things.csv")
DEFAULT_OUT = Path("assets/best-things.json")

# Allowed categories (exact match after alias normalization)
CANON_CATEGORIES = {
    "tours & experiences": "Tours & Experiences",
    "events and venues": "Events and Venues",
    "wellness & aesthetics": "Wellness & Aesthetics",
}
# Light aliasing/typo tolerance (extend as needed)
CATEGORY_ALIASES = {
    "tours and experiences": "tours & experiences",
    "tours & experience": "tours & experiences",
    "events & venues": "events and venues",
    "events": "events and venues",
    "venues": "events and venues",
    "wellness and aesthetics": "wellness & aesthetics",
    "wellness": "wellness & aesthetics",
    "aesthetics": "wellness & aesthetics",
}

REQUIRED_COLUMNS = [
    "id","category","title","subtitle","url","image_url","area","tags","cta_label",
    "priority","status","start_date","end_date","is_sponsored","sponsor_name",
    "utm_source","utm_medium","utm_campaign","notes",
]
# Optional columns (not enforced): rating, is_open

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)

def warn(msg: str):
    print(f"[warn] {msg}", file=sys.stderr)

def is_http(u: str) -> bool:
    return isinstance(u, str) and u.lower().startswith(("http://", "https://"))

def normalize_category(raw: str) -> str | None:
    if not raw: return None
    k = raw.strip().lower()
    k = CATEGORY_ALIASES.get(k, k)
    return CANON_CATEGORIES.get(k)

def parse_bool(s: str) -> bool:
    return str(s).strip().lower() in {"1","true","yes","y","t"}

def parse_int(s: str, default: int = 999) -> int:
    try:
        return int(str(s).strip())
    except Exception:
        return default

def add_utms(url: str, row: dict) -> str:
    parts = list(urlsplit(url))
    q = dict(parse_qsl(parts[3]))
    for k in ("utm_source","utm_medium","utm_campaign"):
        v = (row.get(k) or "").strip()
        if v:
            q[k] = v
    parts[3] = urlencode(q, doseq=True)
    return urlunsplit(parts)

def in_date_window(row: dict, today_iso: str) -> bool:
    sd = (row.get("start_date") or "").strip()
    ed = (row.get("end_date") or "").strip()
    def ok(d: str) -> bool:
        return (not d) or DATE_RE.match(d) is not None
    if not ok(sd) or not ok(ed):
        # If dates are malformed, treat as not in window (safer)
        return False
    if sd and today_iso < sd:  # before start
        return False
    if ed and today_iso > ed:  # after end
        return False
    return True

def split_tags(s: str) -> list[str]:
    if not s: return []
    # split by semicolon or comma; strip empties
    parts = [p.strip() for p in re.split(r"[;,]", s)]
    return [p for p in parts if p]

def validate_header(header: list[str]):
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        die(f"CSV missing required columns: {', '.join(missing)}")

def build_item(row: dict) -> dict:
    # Basic cleaned fields
    cat = normalize_category(row.get("category",""))
    title = (row.get("title") or "").strip()
    subtitle = (row.get("subtitle") or "").strip()
    url = (row.get("url") or "").strip()
    image_url = (row.get("image_url") or "").strip()
    area = (row.get("area") or "").strip()
    cta_label = (row.get("cta_label") or "").strip()
    prio = parse_int(row.get("priority"), default=999)
    sponsored = parse_bool(row.get("is_sponsored", ""))

    # Final URL with UTM params appended (if present)
    url = add_utms(url, row)

    item = {
        "id": (row.get("id") or "").strip(),
        "category": cat,                      # canonical (one of 3)
        "title": title,
        "subtitle": subtitle,
        "url": url,
        "image_url": image_url,
        "area": area or None,
        "tags": split_tags(row.get("tags","")),
        "cta_label": cta_label or "Learn more",
        "priority": prio,
        "is_sponsored": sponsored,
        "sponsor_name": (row.get("sponsor_name") or "").strip() or None,
        # Keep raw timing/meta (not strictly needed by FE but useful if you want badges)
        "start_date": (row.get("start_date") or "").strip() or None,
        "end_date": (row.get("end_date") or "").strip() or None,
        "notes": (row.get("notes") or "").strip() or None,
    }

    # Optional UI fields (already normalized in the read loop)
    if row.get("rating") is not None:
        item["rating"] = row["rating"]
    if row.get("is_open") is not None:
        item["is_open"] = row["is_open"]

    # Drop keys that are None/empty lists to keep JSON clean
    for k in list(item.keys()):
        if item[k] in ("", None, []) and k not in ("subtitle",):  # allow empty subtitle
            item.pop(k, None)
    return item

def main():
    ap = argparse.ArgumentParser(description="Build best-things.json from best_things.csv")
    ap.add_argument("--src", default=str(DEFAULT_SRC), help="CSV path (default: data/homepage/best_things.csv)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Output JSON path (default: assets/best-things.json)")
    ap.add_argument("--cap-per-cat", type=int, default=12, help="Max items per category (default: 12; 0 = unlimited)")
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    if not src.exists():
        die(f"CSV not found: {src}")

    today = date.today().isoformat()

    rows_live: list[dict] = []
    with src.open("r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        header = rdr.fieldnames or []
        validate_header(header)

        for r in rdr:
            # normalize keys→values to strings
            r = {k: (v or "").strip() for k, v in r.items()}

            # status filter
            if (r.get("status") or "").strip().lower() != "live":
                continue
            # date window filter
            if not in_date_window(r, today):
                continue

            # category normalization & validation
            cat = normalize_category(r.get("category",""))
            if not cat:
                warn(f"Skipping row with bad category: {r.get('category')!r} (id={r.get('id')})")
                continue

            # url/image validation
            if not is_http(r.get("url","")) or not is_http(r.get("image_url","")):
                warn(f"Skipping row with invalid url/image_url (id={r.get('id')})")
                continue

            # attach canonical category for sorting/capping
            r["_canon_cat"] = cat
            # safe priority
            r["_priority"] = parse_int(r.get("priority"), default=999)

            # NEW: Normalize optional UI fields
            # rating (float) and is_open (bool)
            try:
                r["rating"] = float((r.get("rating") or "").strip()) if (r.get("rating") or "").strip() else None
            except Exception:
                r["rating"] = None

            iso = (r.get("is_open") or "").strip().lower()
            if iso in ("true", "yes", "1"):
                r["is_open"] = True
            elif iso in ("false", "no", "0"):
                r["is_open"] = False
            else:
                r["is_open"] = None

            rows_live.append(r)

    # Sort: by category (stable), then priority, then title
    rows_live.sort(key=lambda x: (x["_canon_cat"], x["_priority"], x.get("title","").lower()))

    # Cap per category if requested
    capped: list[dict] = []
    seen_per_cat: dict[str, int] = {}
    cap = int(args.cap_per_cat or 0)
    for r in rows_live:
        cat = r["_canon_cat"]
        count = seen_per_cat.get(cat, 0)
        if cap and count >= cap:
            continue
        capped.append(r)
        seen_per_cat[cat] = count + 1

    # Build final payload (strip helper keys)
    items = []
    for r in capped:
        for k in ("_canon_cat","_priority"):
            r.pop(k, None)
        items.append(build_item(r))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(items)} items → {out}")

if __name__ == "__main__":
    main()
