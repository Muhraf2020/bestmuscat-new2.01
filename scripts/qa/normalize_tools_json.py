#!/usr/bin/env python3
import json
from pathlib import Path

TOOLS = Path("data/tools.json")

def norm_about(val):
    # Already correct
    if val is None or isinstance(val, dict):
        return val
    # Legacy array form (1–2 strings)
    if isinstance(val, list):
        short = val[0] if len(val) > 0 and isinstance(val[0], str) else None
        long  = val[1] if len(val) > 1 and isinstance(val[1], str) else None
        if short or long:
            return {"short": short, "long": long}
        return None
    # Single string: treat as short
    if isinstance(val, str):
        s = val.strip()
        return {"short": s, "long": None} if s else None
    # Anything else → drop
    return None

def main():
    if not TOOLS.exists():
        print("No data/tools.json found; nothing to normalize.")
        return
    data = json.loads(TOOLS.read_text(encoding="utf-8"))
    changed = 0
    for i, item in enumerate(data):
        if "about" in item:
            before = item["about"]
            after = norm_about(before)
            if before != after:
                item["about"] = after
                changed += 1
    if changed:
        TOOLS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Normalized 'about' on {changed} item(s).")
    else:
        print("No 'about' fields needed normalization.")

if __name__ == "__main__":
    main()
