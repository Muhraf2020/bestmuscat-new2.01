# FILE: scripts/generate_sitemap.py
import json, pathlib, re, datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "tools.json"
SITEMAP = ROOT / "sitemap.xml"
SITE = "https://bestmuscat.com"

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

def slugify(s): return re.sub(r'(^-|-$)', '', re.sub(r'[^a-z0-9]+','-', (s or '').lower()))
def cat2alias(c): return CATEGORY_ALIAS.get(slugify(c), slugify(c))

def main():
    items = json.loads(DATA.read_text(encoding="utf-8"))
    cats = sorted({slugify((it.get("categories") or ["places"])[0]) for it in items})
    today = datetime.date.today().isoformat()

    urls = []
    urls.append(f"<url><loc>{SITE}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>")
    for c in cats:
        alias = cat2alias(c)
        urls.append(f"<url><loc>{SITE}/{alias}/</loc><changefreq>daily</changefreq><priority>0.8</priority></url>")
    for it in items:
        slug = slugify(it.get("slug") or it.get("name") or "")
        if not slug: continue
        cat = slugify((it.get("categories") or ["places"])[0])
        alias = cat2alias(cat)
        urls.append(
            f"<url><loc>{SITE}/{alias}/{slug}/</loc>"
            f"<lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.6</priority></url>"
        )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{''.join(urls)}
</urlset>"""
    SITEMAP.write_text(xml, encoding="utf-8")

if __name__ == "__main__":
    main()
