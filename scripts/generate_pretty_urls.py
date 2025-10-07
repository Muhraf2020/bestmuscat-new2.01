# FILE: scripts/generate_pretty_urls.py
import json, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "tools.json"
OUT  = ROOT  # write stubs into the site root

# Keep in sync with assets/seo-routes.js
CATEGORY_ALIAS = {
    "hotels": "places-to-stay",
    "restaurants": "places-to-eat",
    "schools": "schools",
    "spas": "spas",
    "clinics": "clinics",
    "malls": "shopping-malls",
    "car-repair-garages": "car-repair-garages",
    "home-maintenance-and-repair": "home-maintenance-and-repair",
    "catering-services": "catering-services",
    "events": "events-planning",
    "events-planning": "events-planning",
    "moving-and-storage": "moving-and-storage",
}

def slugify(s):
    return re.sub(r'(^-|-$)', '', re.sub(r'[^a-z0-9]+', '-', (s or '').lower()))

def category_to_alias(cat):
    s = slugify(cat)
    return CATEGORY_ALIAS.get(s, s)

def stub_html(canonical_url, redirect_url):
    return f"""<!doctype html>
<meta charset="utf-8">
<link rel="canonical" href="{canonical_url}">
<meta http-equiv="refresh" content="0; url={redirect_url}">
<script>location.replace({redirect_url!r});</script>
<p>Redirecting to <a href="{redirect_url}">{canonical_url}</a>…</p>
"""

def ensure_dir(p): pathlib.Path(p).mkdir(parents=True, exist_ok=True)
def write(p, s): p.write_text(s, encoding="utf-8")

def main():
    items = json.loads(DATA.read_text(encoding="utf-8"))

    # 1) Category stubs
    primary_cats = set()
    for it in items:
        cats = it.get("categories") or []
        if cats:
            primary_cats.add(slugify(cats[0]))
    for cat in sorted(primary_cats):
        alias = category_to_alias(cat)
        folder = OUT / alias
        ensure_dir(folder)
        canonical = f"/{alias}/"
        redirect = f"/index.html?category={cat}"
        write(folder / "index.html", stub_html(canonical, redirect))

    # 2) Item stubs
    for it in items:
        slug = slugify(it.get("slug") or it.get("name") or "")
        if not slug:
            continue
        cat = slugify((it.get("categories") or ["places"])[0])
        alias = category_to_alias(cat)
        folder = OUT / alias / slug
        ensure_dir(folder)
        canonical = f"/{alias}/{slug}/"
        redirect = f"/tool.html?slug={slug}"
        write(folder / "index.html", stub_html(canonical, redirect))

if __name__ == "__main__":
    main()
