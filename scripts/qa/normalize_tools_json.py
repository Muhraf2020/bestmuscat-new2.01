#!/usr/bin/env python3
import json
from pathlib import Path

TOOLS = Path("data/tools.json")

# ---------- ABOUT NORMALIZATION ----------
def norm_about(val):
    # Already correct
    if val is None or isinstance(val, dict):
        return val
    # Legacy array [short, long]
    if isinstance(val, list):
        short = val[0] if len(val) > 0 and isinstance(val[0], str) else None
        long  = val[1] if len(val) > 1 and isinstance(val[1], str) else None
        return {"short": short, "long": long} if (short or long) else None
    # Single string -> short
    if isinstance(val, str):
        s = val.strip()
        return {"short": s, "long": None} if s else None
    return None

def synthesize_about_if_missing(item):
    if isinstance(item.get("about"), dict) or item.get("about") is None:
        return False
    tag = item.get("tagline")
    desc = item.get("description")
    if tag or desc:
        item["about"] = {"short": tag or None, "long": desc or None}
        return True
    return False

# ---------- HOURS NORMALIZATION ----------
LEGACY_DAYS_TITLE = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
DAYS_MAP = {
    "Mon":"mon","Tue":"tue","Wed":"wed","Thu":"thu","Fri":"fri","Sat":"sat","Sun":"sun"
}

def is_time_pair(x):
    # ["09:00","17:00"]
    return isinstance(x, list) and len(x) == 2 and all(isinstance(t, str) for t in x)

def legacy_hours_to_weekly(hours_obj):
    weekly = {}
    for dtitle in LEGACY_DAYS_TITLE:
        slots = hours_obj.get(dtitle)
        if not slots:
            continue
        # slots may be a list of pairs or a single pair
        normalized = []
        if isinstance(slots, list) and len(slots) and all(isinstance(s, list) for s in slots):
            # e.g. [["09:00","12:00"], ["13:00","17:00"]]
            for pair in slots:
                if is_time_pair(pair):
                    normalized.append({"open": pair[0], "close": pair[1]})
        elif is_time_pair(slots):
            normalized.append({"open": slots[0], "close": slots[1]})
        # assign if any
        if normalized:
            weekly[DAYS_MAP[dtitle]] = normalized
    return weekly

def norm_hours(val):
    # accept null
    if val is None:
        return None
    # new format already?
    if isinstance(val, dict) and "weekly" in val:
        # ensure weekly has only lowercase keys and objects {open,close}
        weekly = val.get("weekly") or {}
        fixed_weekly = {}
        for k, arr in weekly.items():
            if not arr:
                continue
            out = []
            for s in (arr if isinstance(arr, list) else []):
                if isinstance(s, dict) and "open" in s and "close" in s:
                    out.append({"open": s["open"], "close": s["close"]})
                elif is_time_pair(s):
                    out.append({"open": s[0], "close": s[1]})
            if out:
                fixed_weekly[k.lower()] = out
        tz = val.get("tz") or "Asia/Muscat"
        return {"tz": tz, "weekly": fixed_weekly} if fixed_weekly else {"tz": tz, "weekly": {}}
    # legacy title-case days present?
    if isinstance(val, dict) and any(d in val for d in LEGACY_DAYS_TITLE):
        weekly = legacy_hours_to_weekly(val)
        tz = val.get("tz") or "Asia/Muscat"
        return {"tz": tz, "weekly": weekly}
    # array form: [{days, open, close}, ...] -> expand to weekly
    if isinstance(val, list):
        weekly = {}
        for slot in val:
            if not isinstance(slot, dict): 
                continue
            days = (slot.get("days") or "").strip()
            o, c = slot.get("open"), slot.get("close")
            if not (days and isinstance(o, str) and isinstance(c, str)):
                continue
            # very simple mapping: split by commas and map to lower keys
            for d in days.split(","):
                d = d.strip().lower()[:3]
                key = {"mon":"mon","tue":"tue","wed":"wed","thu":"thu","fri":"fri","sat":"sat","sun":"sun"}.get(d)
                if not key: 
                    continue
                weekly.setdefault(key, []).append({"open": o, "close": c})
        return {"tz": "Asia/Muscat", "weekly": weekly}
    # anything else -> leave as null to be safe
    return None

def main():
    if not TOOLS.exists():
        print("No data/tools.json found; nothing to normalize.")
        return
    data = json.loads(TOOLS.read_text(encoding="utf-8"))
    changed = 0

    for item in data:
        # ABOUT
        if "about" in item:
            before = item["about"]
            after = norm_about(before)
            if before != after:
                item["about"] = after
                changed += 1
        else:
            if synthesize_about_if_missing(item):
                changed += 1

        # HOURS
        if "hours" in item:
            before = item["hours"]
            after = norm_hours(before)
            if before != after:
                item["hours"] = after
                changed += 1

    if changed:
        TOOLS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Normalized fields on {changed} item(s).")
    else:
        print("No fields needed normalization.")

if __name__ == "__main__":
    main()
