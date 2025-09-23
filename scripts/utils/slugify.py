import re, unicodedata
def slugify(name, neighborhood=None):
    base = f"{name} {neighborhood or ''}".strip().lower()
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return re.sub(r"-{2,}", "-", base)
