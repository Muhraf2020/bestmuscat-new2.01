// FILE: assets/curated.js
(function () {
  const qs = new URLSearchParams(location.search);
  const listSlug = qs.get("list") || "";

  const elTitle = document.getElementById("c-title");
  const elIntro = document.getElementById("c-intro");
  const elGrid  = document.getElementById("c-grid");
  const elJSON  = document.getElementById("jsonld-list");

  function esc(s){
    return String(s).replace(/[&<>"']/g, c => (
      {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
    ));
  }
  function initials(name) {
    return (name||"").split(/\s+/).slice(0,2).map(p=>p[0]?.toUpperCase()||"").join("") || "BM";
  }

  // Prefer your pretty routes if present, else fallback to /tool.html?slug=...
  function prettyItemUrl(siteUrl, primaryCat, slug) {
    const base = (siteUrl || (location.origin + "/")).replace(/\/$/, "/");
    if (window.SEO_ROUTES && typeof SEO_ROUTES.prettyItemUrl === "function") {
      return SEO_ROUTES.prettyItemUrl(base, primaryCat, slug);
    }
    return `${base}tool.html?slug=${encodeURIComponent(slug)}`;
  }

  async function run() {
    try {
      const [toolsRes, curRes] = await Promise.all([
        fetch("data/tools.json?ts=" + Date.now(), { cache: "no-store" }),
        fetch("data/curations.json?ts=" + Date.now(), { cache: "no-store" })
      ]);
      if (!toolsRes.ok || !curRes.ok) throw new Error("Failed to load data");

      const tools = await toolsRes.json();
      const curations = await curRes.json();

      const bySlug = Object.fromEntries((tools||[]).map(t => [t.slug, t]));
      const curation = (curations || []).find(c => c.slug === listSlug);

      if (!curation) {
        document.title = "List not found — Best Muscat";
        elTitle.textContent = "List not found";
        elIntro.textContent = "The curated list you requested doesn’t exist.";
        elGrid.innerHTML = `<div class="empty">Try a different list.</div>`;
        return;
      }

      // Page chrome
      document.title = `${curation.title} — Best Muscat`;
      elTitle.textContent = curation.title || "Curated List";
      elIntro.textContent = curation.intro || "";

      // Render items in the order defined by the curation
      const cards = (curation.items || []).map(entry => {
        const rec = bySlug[entry.slug] || {};
        const name = rec.name || entry.slug;
        const primaryCat = (rec.categories && rec.categories[0]) || "places";
        const detailUrl = prettyItemUrl("https://bestmuscat.com/", primaryCat, entry.slug);

        const title = esc(name);
        const subtitle = esc(rec.tagline || rec.short_description || rec.description || "");

        // tags
        const tagsHTML = (rec.tags || []).slice(0,5).map(t => `<span class="tag">${esc(t)}</span>`).join("");

        // image: prefer local path; if remote/missing → initials block
        const hero = (rec.image || (rec.images && (rec.images.hero || rec.images.card)) || "").trim();
        const useLocal = hero && !/^https?:\/\//i.test(hero);

        const imgHtml = useLocal
          ? `
          <a href="${detailUrl}" class="card-img" aria-label="${title} details">
            <img src="${esc(hero)}" alt="${title}" loading="lazy" decoding="async"
              onerror="
                const wrap = this.closest('.card-img');
                if (wrap) { wrap.classList.add('img-fallback'); wrap.innerHTML = '<div class=&quot;img-placeholder&quot;>${esc(initials(name))}</div>'; }
              "
            />
          </a>`
          : `
          <a href="${detailUrl}" class="card-img img-fallback" aria-label="${title} details">
            <div class="img-placeholder">${esc(initials(name))}</div>
          </a>`;

        // sponsored badge (optional)
        const sponsored = entry.sponsored ? `<span class="badge" title="Paid placement">Sponsored</span>` : "";

        // CTAs
        const website = rec.website || rec.url || "";
        let websiteIsReal = false;
        try {
          const u = new URL(website);
          websiteIsReal = /^https?:$/i.test(u.protocol) && !/(\.|^)example\.com$/i.test(u.hostname);
        } catch {}
        const ctas = [
          websiteIsReal ? `<a class="link-btn" href="${esc(website)}" target="_blank" rel="noopener">Website</a>` : "",
          `<a class="link-btn" href="${detailUrl}">View</a>`
        ].filter(Boolean).join(" ");

        return `
          <article class="card card--place">
            ${imgHtml}
            <div class="card-body">
              <h2 class="card-title"><a href="${detailUrl}" class="card-link">${title}</a></h2>
              <p class="card-sub">${subtitle}</p>
              <div class="tags">${tagsHTML} ${sponsored}</div>
              <div class="ctas">${ctas}</div>
            </div>
          </article>
        `;
      });

      // If every listed slug is unknown, show a friendly message instead of a blank page
      if (!cards.length) {
        elGrid.innerHTML = `<div class="empty">This list has no items yet. Add some slugs to <code>data/curations.json</code>.</div>`;
      } else {
        elGrid.innerHTML = cards.join("");
      }

      // JSON-LD ItemList
      const itemList = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": curation.title,
        "itemListElement": (curation.items || []).map((entry, i) => {
          const rec = bySlug[entry.slug] || {};
          const primaryCat = (rec.categories && rec.categories[0]) || "places";
          const url = prettyItemUrl("https://bestmuscat.com/", primaryCat, entry.slug);
          return { "@type": "ListItem", "position": i + 1, "url": url };
        })
      };
      elJSON.textContent = JSON.stringify(itemList);

    } catch (e) {
      console.warn("[curated.js] failed:", e);
      elGrid.innerHTML = `<div class="empty">Couldn’t load curated list. Check <code>data/curations.json</code> and <code>data/tools.json</code>.</div>`;
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
