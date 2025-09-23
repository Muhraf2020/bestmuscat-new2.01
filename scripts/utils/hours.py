# scripts/utils/hours.py
import re
from typing import Dict, List

DAY_ALIASES = {
    "mon": "mon", "monday": "mon", "mon.": "mon",
    "tue": "tue", "tuesday": "tue", "tues": "tue",
    "wed": "wed", "wednesday": "wed",
    "thu": "thu", "thursday": "thu", "thur": "thu", "thurs": "thu",
    "fri": "fri", "friday": "fri",
    "sat": "sat", "saturday": "sat",
    "sun": "sun", "sunday": "sun",
    "daily": "daily", "everyday": "daily",
}
ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

_time_re = re.compile(r"^(2[0-3]|[01]?\d):([0-5]\d)$")

def _parse_time(s: str) -> str:
    s = s.strip()
    if not _time_re.match(s):
        raise ValueError(f"Invalid time: {s}")
    hh, mm = s.split(":")
    return f"{int(hh):02d}:{int(mm):02d}"

def parse_hours(compact: str, tz: str = "Asia/Muscat") -> Dict:
    """
    Parse compact human-friendly hours into a normalized weekly structure.

    Input examples:
      - "Daily 10:00-22:00"
      - "Mon-Thu 08:30-16:00; Fri 08:30-12:00; Sat-Sun closed"
      - "Mon 09:00-18:00; Tue 09:00-18:00; Wed-Sun closed"

    Returns:
      {
        "tz": "Asia/Muscat",
        "weekly": {
          "mon": [{"open":"08:30","close":"16:00"}],
          "tue": [...],
          ...
        }
      }
    """
    weekly: Dict[str, List[Dict[str, str]]] = {d: [] for d in ORDER}
    if not compact or not compact.strip():
        return {"tz": tz, "weekly": weekly}

    groups = [g.strip() for g in compact.split(";") if g.strip()]
    for group in groups:
        # Expect "<days> <hours>", e.g. "Mon-Thu 08:30-16:00, 18:00-22:00"
        if " " not in group:
            continue
        days_part, hours_part = group.split(" ", 1)

        # Expand days
        days: List[str] = []
        for token in days_part.split(","):
            token = token.strip().lower()
            token = DAY_ALIASES.get(token, token)
            if token == "daily":
                days.extend(ORDER)
            elif "-" in token:  # range e.g., mon-thu
                a, b = token.split("-", 1)
                a = DAY_ALIASES.get(a, a)
                b = DAY_ALIASES.get(b, b)
                if a in ORDER and b in ORDER:
                    i1, i2 = ORDER.index(a), ORDER.index(b)
                    if i1 <= i2:
                        days.extend(ORDER[i1:i2 + 1])
                    else:  # wrap-around (rare)
                        days.extend(ORDER[i1:] + ORDER[:i2 + 1])
            else:
                if token in ORDER:
                    days.append(token)
        if not days:
            continue

        hours_part = hours_part.strip().lower()
        if hours_part in {"closed", "close", "off", "—", "-"}:
            # explicit closed → no intervals
            continue

        # Multiple intervals allowed, comma-separated
        intervals = [h.strip() for h in hours_part.split(",") if h.strip()]
        parsed_intervals: List[Dict[str, str]] = []
        for interval in intervals:
            if "-" not in interval:
                continue
            o, c = interval.split("-", 1)
            o, c = _parse_time(o), _parse_time(c)
            parsed_intervals.append({"open": o, "close": c})

        for d in days:
            weekly[d].extend(parsed_intervals)

    return {"tz": tz, "weekly": weekly}

__all__ = ["parse_hours"]
