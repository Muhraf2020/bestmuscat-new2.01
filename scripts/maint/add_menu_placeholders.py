#!/usr/bin/env python3
import argparse, json, sys, copy, datetime, pathlib

DEFAULT_PLACEHOLDER = {
    "menu": {
        "status": "placeholder",          # placeholder | scraped | verified
        "source": {"type": "unknown", "url": "", "captured_at": None},  # talabat|zomato|website|unknown
        "currency": "AED",
        "last_updated": None,             # ISO8601
        "sections": [
            {
                "title": "Featured",
                "items": [
                    {"name": "TBA", "price": None, "desc": "", "tags": []}
                ]
            }
        ],
        "notes": "Auto-added placeholder. Replace with real menu data."
    }
}

def is_restaurant(obj):
    cats = obj.get("categories") or obj.get("category") or []
    if isinstance(cats, str):
        cats = [cats]
    cats_norm = {str(c).strip().lower() for c in cats}
    return "restaurants" in cats_norm

def ensure_menu_placeholder(obj, now_iso, currency):
    if not isinstance(obj, dict):
        return False, "not an object"

    if not is_restaurant(obj):
        return False, "not a restaurant"

    if "menu" in obj and isinstance(obj["menu"], dict):
        return False, "already has menu"

    menu = copy.deepcopy(DEFAULT_PLACEHOLDER["menu"])
    menu["currency"] = currency
    menu["last_updated"] = now_iso
    obj["menu"] = menu
    return True, "added"

def resolve_data_path(cli_path: str | None) -> pathlib.Path:
    if cli_path:
        p = pathlib.Path(cli_path)
        if p.exists():
            return p
        sys.exit(f"ERROR: --file not found: {cli_path}")

    # try common locations from repo root
    candidates = [
        pathlib.Path("data/tools.json"),
        pathlib.Path("bestmuscat-new/data/tools.json"),
    ]
    for cand in candidates:
        if cand.exists():
            return cand

    sys.exit("ERROR: Could not find tools.json. Tried:\n  " + "\n  ".join(map(str, candidates)))

def main():
    ap = argparse.ArgumentParser(description="Add menu placeholders to restaurant records")
    ap.add_argument("--file", help="Path to JSON file (array of place objects)")
    ap.add_argument("--write", action="store_true", help="Actually write changes")
    ap.add_argument("--currency", default="AED", help="Currency code for placeholders")
    args = ap.parse_args()

    p = resolve_data_path(args.file)

    try:
        text = p.read_text(encoding="utf-8")
        data = json.loads(text)
    except FileNotFoundError:
        sys.exit(f"ERROR: File not found: {p}")
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: JSON parse failed: {e}")

    if not isinstance(data, list):
        sys.exit("ERROR: Expected a JSON array of place objects at top level.")

    now_iso = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    # walk & modify
    total = len(data)
    total_restaurants = 0
    added = 0
    skipped_has_menu = 0
    skipped_not_restaurant = 0
    changed_ids = []

    for obj in data:
        if is_restaurant(obj):
            total_restaurants += 1
        ok, reason = ensure_menu_placeholder(obj, now_iso, args.currency)
        if ok:
            added += 1
            changed_ids.append(obj.get("slug") or obj.get("id"))
        else:
            if reason == "already has menu":
                skipped_has_menu += 1
            elif reason == "not a restaurant":
                skipped_not_restaurant += 1

    # report
    print(f"Scanned: {total} records")
    print(f"Restaurants detected: {total_restaurants}")
    print(f"Added placeholders: {added}")
    print(f"Skipped (already had menu): {skipped_has_menu}")
    print(f"Skipped (not restaurants): {skipped_not_restaurant}")
    if changed_ids:
        print("First few changed:", ", ".join(map(str, changed_ids[:10])))

    if not args.write:
        print("\n[dry-run] No changes written. Re-run with --write to apply.")
        return

    # backup and write
    bak = p.with_suffix(p.suffix + f".bak.{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}")
    p.rename(bak)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote changes to {p} (backup at {bak}).")

if __name__ == "__main__":
    main()
