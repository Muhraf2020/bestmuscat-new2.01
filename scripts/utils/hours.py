import re
Input examples:
- "Daily 10:00-22:00"
- "Mon-Thu 08:30-16:00; Fri 08:30-12:00; Sat-Sun closed"
- "Mon 09:00-18:00; Tue 09:00-18:00; Wed-Sun closed"
Returns:
{"tz": tz, "weekly": {day: [{open,close}, ...]}}
"""
weekly: Dict[str, List[Dict[str,str]]] = {d: [] for d in ORDER}
if not compact or not compact.strip():
return {"tz": tz, "weekly": weekly}


groups = [g.strip() for g in compact.split(";") if g.strip()]
for group in groups:
# split days and times by first space
if " " not in group:
continue
days_part, hours_part = group.split(" ", 1)


# expand days
days = []
for token in days_part.split(","):
token = token.strip().lower()
token = DAY_ALIASES.get(token, token)
if token == "daily":
days.extend(ORDER)
elif "-" in token: # range e.g., mon-thu
a,b = token.split("-",1)
a = DAY_ALIASES.get(a, a)
b = DAY_ALIASES.get(b, b)
try:
i1, i2 = ORDER.index(a), ORDER.index(b)
except ValueError:
continue
if i1 <= i2:
days.extend(ORDER[i1:i2+1])
else: # wrap (not typical but support)
days.extend(ORDER[i1:]+ORDER[:i2+1])
else:
if token in ORDER:
days.append(token)
if not days:
continue


hours_part = hours_part.strip().lower()
if hours_part in {"closed","close","off","—","-"}:
# nothing to add (explicit closed)
continue


# support multiple intervals separated by ","
intervals = [h.strip() for h in hours_part.split(",") if h.strip()]
parsed_intervals = []
for interval in intervals:
if "-" not in interval:
continue
o,c = interval.split("-",1)
o, c = _parse_time(o), _parse_time(c)
parsed_intervals.append({"open": o, "close": c})
for d in days:
weekly[d].extend(parsed_intervals)


return {"tz": tz, "weekly": weekly}
