/* FILE: assets/best-things.js
 * Renders the "Best Things to Do in Muscat" section from assets/best-things.json
 * while preserving the previous layout:
 *  - Tabs (Tours & Experiences / Events and Venues / Wellness & Aesthetics)
 *  - Featured card (large, left)
 *  - Top 5 listings (right column)
 */

(function () {
  const JSON_URL = "assets/best-things.json";

  // Map JSON categories → tab data-cat keys already used in index.html
  const CAT_MAP = {
    "Tours & Experiences": "tours",
    "Events and Venues": "events",
    "Wellness & Aesthetics": "wellness",
  };

  // Elements
  const section = document.getElementById("best-things");
  if (!section) return;
  const featuredEl = section.querySelector("#featured-card");
  const listingsEl = section.querySelector("#top-listings");

  // Small helpers
  const clean = (s) => (s || "").toString().trim();
  const imgFallback =
    "assets/placeholders/placeholder-16x9.webp"; // make sure this exists

  function aEl(href, text, cls) {
    const a = document.createElement("a");
    if (cls) a.className = cls;
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = text;
    return a;
  }

  // FEATURED CARD (left)
  function renderFeatured(item) {
    const title = clean(item.title);
    const sub = clean(item.subtitle);
    const area = clean(item.area);
    const url = clean(item.url);
    const img = clean(item.image_url) || imgFallback;

    featuredEl.innerHTML = `
      <img src="${img}"
           alt="${title.replace(/"/g, "&quot;")}"
           loading="lazy" decoding="async"
           onerror="this.onerror=null;this.src='${imgFallback}';">
      <div class="content">
        <div class="rank">${item.badge || ""}</div>
        <h3 class="name">${title}</h3>
        <div class="meta">
          ${area ? `<span>${area}</span>` : ""}
          ${sub ? (area ? " · " : "") + `<span>${sub}</span>` : ""}
        </div>
        ${item.is_sponsored ? `<div class="sponsored">Sponsored</div>` : ""}
        ${clean(item.description)
          ? `<p class="desc">${clean(item.description)}</p>`
          : ""}
        ${
          // If you ever add numeric scoring back into the CSV/JSON, show it.
          item.overall || (item.scores && Object.keys(item.scores || {}).length)
            ? renderScoreBox(item)
            : ""
        }
        <div class="cta-row">
          ${url ? aEl(url, item.cta_label || "Learn more", "btn").outerHTML : ""}
        </div>
      </div>
    `;
  }

  function renderScoreBox(item) {
    const overall = Number(item.overall || 0);
    const scores = item.scores || {}; // { "Quality": 9.5, ... }
    const lines = Object.keys(scores)
      .map((k) => {
        const v = Number(scores[k]);
        if (!isFinite(v)) return "";
        return `<span><span>${k}</span>&nbsp;<span>${v.toFixed(2)}</span></span>`;
      })
      .join("");
    if (!lines && !isFinite(overall)) return "";
    return `
      <div class="score-box">
        ${
          isFinite(overall)
            ? `<div class="score-summary">${overall.toFixed(
                2
              )}<small>/10</small></div>`
            : ""
        }
        <div class="score-breakdown">${lines}</div>
      </div>
    `;
  }

  // RIGHT COLUMN LIST (top 5)
  function renderListings(list) {
    const html = (list || [])
      .slice(0, 5)
      .map((item) => {
        const title = clean(item.title);
        const sub = clean(item.subtitle);
        const area = clean(item.area);
        const img = clean(item.image_url) || imgFallback;
        const url = clean(item.url);

        const meta = [area, sub].filter(Boolean).join(" · ");

        return `
          <a class="listing-card" href="${url}" target="_blank" rel="noopener" aria-label="${title.replace(
          /"/g,
          "&quot;"
        )}">
            <img src="${img}" alt="${title.replace(/"/g, "&quot;")}"
                 loading="lazy" decoding="async"
                 onerror="this.onerror=null;this.src='${imgFallback}';">
            <div class="info">
              <div class="name">${title}</div>
              <div class="sub">${meta}</div>
              ${
                item.is_sponsored
                  ? `<div class="status sponsored">Sponsored</div>`
                  : ""
              }
            </div>
            ${
              // If you store a numeric score, show on the right.
              isFinite(Number(item.score))
                ? `<div class="score">${Number(item.score).toFixed(2)}</div>`
                : ""
            }
          </a>
        `;
      })
      .join("");

    listingsEl.innerHTML = html;
  }

  function setActiveTab(key) {
    section
      .querySelectorAll(".tabs .tab")
      .forEach((b) => b.classList.toggle("active", b.dataset.cat === key));
  }

  function wireTabs(byKey) {
    section.querySelectorAll(".tabs .tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.cat;
        setActiveTab(key);
        const items = byKey.get(key) || [];
        renderFeatured(items[0] || {});
        renderListings(items.slice(1));
      });
    });
  }

  async function load() {
    try {
      // Cache-bust to avoid GitHub Pages CDN staleness
      const res = await fetch(`${JSON_URL}?_=${Date.now()}`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const rows = (await res.json()) || [];

      // Group rows by tab key
      const byKey = new Map();
      for (const r of rows) {
        const key = CAT_MAP[clean(r.category)] || "";
        if (!key) continue;
        if (!byKey.has(key)) byKey.set(key, []);
        byKey.get(key).push(r);
      }

      // Sort each group by priority asc, then title (if your JSON includes it)
      for (const [k, arr] of byKey.entries()) {
        arr.sort((a, b) => {
          const pa = Number(a.priority || 999);
          const pb = Number(b.priority || 999);
          if (pa !== pb) return pa - pb;
          return clean(a.title).localeCompare(clean(b.title));
        });
      }

      // Wire tabs and render initial active tab
      wireTabs(byKey);
      const active = section.querySelector(".tabs .tab.active");
      const initialKey = active?.dataset?.cat || "tours";
      setActiveTab(initialKey);
      const items = byKey.get(initialKey) || [];
      renderFeatured(items[0] || {});
      renderListings(items.slice(1));
    } catch (err) {
      console.error("Best Things loader failed:", err);
      featuredEl.innerHTML =
        "<p style='padding:16px'>Content unavailable right now.</p>";
      listingsEl.innerHTML = "";
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
