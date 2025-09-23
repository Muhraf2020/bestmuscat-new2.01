# Best Muscat Directory (Static)

This repository contains a portable, 100% static directory listing Muscat’s top hotels, restaurants, schools, spas, clinics and malls. The site is built without a back‑end; search, filtering and pagination run entirely client‑side in the browser.

## How to use

1. Open `index.html` in a web browser to browse the directory. You can search by name, category or tag, and filter by category using the chips at the top.
2. Each place has its own detail page at `tool.html?slug=…` (linked from every card). Metadata for these pages is updated on the fly for SEO.
3. Add or edit listings in `data/tools.json`. Each item must belong to exactly one of the six core categories listed below.

## Publish on GitHub Pages (or any static host)

* Push the files in this directory to a public repository.
* In **Settings → Pages**, choose **Deploy from a branch** → `main` → `/root`.
* Your site goes live at `https://yourname.github.io/best-muscat-directory/` (or your chosen repository name).
* Update `assets/app.js` → `CONFIG.SITE_URL` with your live URL.
* (Optional) For a custom domain, add a CNAME file and configure DNS to point to your GitHub Pages URL.

## Data schema (`data/tools.json`)

Each place in the directory is represented as a JSON object with the following fields:

```json
{
  "id": "string-uuid-or-slug-safe",
  "slug": "kebab-case-unique",
  "name": "Place Name",
  "url": "https://example.com",            // External website or "#" if none
  "tagline": "One-line value proposition",
  "description": "Short paragraph describing the place.",
  "pricing": "free | freemium | paid",    // Currently unused but kept for compatibility
  "categories": ["Hotels"],              // Exactly one of: Hotels, Restaurants, Schools, Spas, Clinics, Malls
  "tags": ["short","keywords"],        // Up to five descriptive tags (e.g. ratings or features)
  "logo": "assets/images/hotels.png",    // Relative path to an image used on the card
  "evidence_cites": false,                // Legacy flags (ignored)
  "local_onprem": false,
  "edu_discount": false,
  "free_tier": false,
  "beta": false,
  "created_at": "YYYY-MM-DD"             // Date string
}
```

## Categories

The Best Muscat directory organizes listings into six core categories:

* **Hotels** – resorts, hotels and serviced apartments.
* **Restaurants** – cafes, fine dining and casual eateries.
* **Schools** – nurseries, primary, secondary and international schools.
* **Spas** – spas, wellness centers and hammams.
* **Clinics** – medical, dental and specialist clinics.
* **Malls** – shopping centres and retail complexes.

## Disclaimer (include on site)

**Places & Links Disclaimer.** The places and external links referenced on this website are provided solely for informational purposes. Inclusion does not constitute endorsement or preference; no affiliate relationships. Features, pricing, availability and policies may change — verify current details before you visit and comply with local regulations. External websites are not under our control; links may change. All trademarks belong to their owners. No warranty is expressed or implied.

---

## Automation & Build Additions

This repository has been enhanced with a lightweight, automation-ready pipeline and safe UI hooks:

- **Data model & schema**: `data/*.json`, `scripts/utils/schema_place.json`
- **QA**: `scripts/qa/*.py`
- **Build**: `scripts/build/*.py` → search index, sitemaps, category shards
- **(Optional) Ingest & Enrich** stubs under `scripts/ingest/` and `scripts/enrich/`
- **AI guardrails** stubs under `scripts/ai/`
- **Media** stubs under `scripts/media/`
- **CI/CD**: `.github/workflows/ci.yml` to validate, build, and deploy to GitHub Pages

### Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# QA + build
python scripts/qa/validate_schema.py
python scripts/qa/missing_fields_report.py
python scripts/build/build_search_index.py
python scripts/build/build_sitemaps.py
python scripts/build/emit_category_feeds.py
```

> The new JS (`assets/app.enhanced.js`) is additive and won’t alter your existing layout. It injects extra sections on detail pages only when it finds standard containers.
