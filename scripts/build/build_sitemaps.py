import json, os, pathlib, datetime
from urllib.parse import quote

BASE_URL = os.getenv("SITE_BASE_URL", "https://<your-domain-or-pages-url>")
places = json.load(open("data/places.json"))
out_dir = pathlib.Path("data/sitemaps"); out_dir.mkdir(parents=True, exist_ok=True)

def url(loc):
    return f"{BASE_URL.rstrip('/')}/{loc.lstrip('/')}"

urls = [url(f"tool.html?slug={p['slug']}") for p in places]
def sm(urls):
    parts = ["<?xml version='1.0' encoding='UTF-8'?>",
             "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"]
    today = datetime.date.today().isoformat()
    for u in urls:
        parts.append(f"<url><loc>{u}</loc><lastmod>{today}</lastmod></url>")
    parts.append("</urlset>")
    return "\n".join(parts)

(open(out_dir/"sitemap-places.xml","w")).write(sm(urls))
(open(out_dir/"sitemap-index.xml","w")).write("""<?xml version='1.0' encoding='UTF-8'?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>""" + url("data/sitemaps/sitemap-places.xml") + """</loc></sitemap>
</sitemapindex>
""")
print("Wrote sitemaps")
