(async function () {
  const qs = new URLSearchParams(location.search);
  const listSlug = qs.get("list") || "";

  const elTitle = document.getElementById("c-title");
  const elIntro = document.getElementById("c-intro");
  const elGrid  = document.getElementById("c-grid");
  const elJSON  = document.getElementById("jsonld-list");

  function esc(s){ return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function initials(name) {
    return (name||"").split(/\s+/).slice(0,2).map(p=>p[0]?.toUpperCase()||"").join("") || "BM";
  }
  function prettyItemUrl(siteUrl, primaryCat, slug) {
    // mirrors your SEO_ROUTES.prettyItemUrl behavior for this page
    const base = (siteUrl || (location.origin + "/")).replace(/\/$/, "/");
    return `${base}${encodeURIComponent(primaryCat)}/${encodeURIComponent(slug)}/`;
  }

  try {
    const [toolsRes, curRes] = await Promise.all([
      fetch("data/tools.json?ts=" + Date.now(), { cache: "no-store" }),
      fetch("data/curations.json?ts=" + Date.now(), { cache: "no-store" })
    ]);
    const tools = await toolsRes.json();
    const curations = await curRes.json();

    const bySlug = Object.fromEntries((tools||[]).map(t => [t.slug, t]));
    const curation = (curations || []).find(c => c.slug === listSlug);

    if (!curation) {
      elTitle.textContent = "List not found";
      elIntro.textContent = "The curated list you requested doesn’t exist.";
      return;
    }

    // Set page text + title
    document.title = curation.title + " — Best Muscat";
    elTitle.textContent = curation.title || "Curated List";
    elIntro.textContent = curation.intro || "";

    // Build cards for the listed slugs (keeps your custom order)
    const items = (curation.items || []).map(entry => {
      const rec = bySlug[entry.slug] || {};
      const primaryCat = (rec.categories && rec.categories[0]) || "places";
      const detailUrl = prettyItemUrl("https://bestmuscat.com/", primaryCat, entry.slug);

      const title = esc(rec.name || entry.slug);
      const subtitle = esc(rec.tagline || rec.short_description || rec.description || "");
      const tags = (rec.tags || []).slice(0,5).map(t=>`<span class="tag">${esc(t)}</span>`).join("");

      // image: prefer local-ish hero if present; else blank to trigger initials
      const hero = (rec.image || (rec.images && (rec.images.hero || rec.images.card)) || "").trim();
      const imgHtml = hero && !/^https?:\/\//i.test(hero)
        ? `
          <a href="${detailUrl}" class="card-img" aria-label="${title} details">
            <img src="${esc(hero)}" alt="${title}" loading="lazy" decoding="async"
              onerror="
                const wrap = this.closest('.card-img');
                if (wrap) { wrap.classList.add('img-fallback'); wrap.innerHTML = '<div class=&quot;img-placeholder&quot;>${esc(initials(rec.name))}</div>'; }
              "
            />
          </a>`
        : `
          <a href="${detailUrl}" class="card-img img-fallback" aria-label="${title} details">
            <div class="img-placeholder">${esc(initials(rec.name))}</div>
          </a>`;

      const sponsored = entry.sponsored ? `<span class="badge" title="Paid placement">Sponsored</span>` : "";

      // CTA: View (always) + Website (if valid and not example.com)
      const website = rec.website || rec.url || "";
      const websiteIsReal = (() => {
        try { const u = new URL(website); return /^(https?:)$/.test(u.protocol) && !/(\.|^)example\.com$/i.test(u.hostname); } catch { return false; }
      })();

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
            <div class="tags">${tags} ${sponsored}</div>
            <div class="ctas">${ctas}</div>
          </div>
        </article>
      `;
    });

    elGrid.innerHTML = items.join("");

    // JSON-LD ItemList for the curated page
    const itemList = {
      "@context": "https://schema.org",
      "@type": "ItemList",
      "name": curation.title,
      "itemListElement": (curation.items || []).map((entry, i) => {
        const rec = bySlug[entry.slug] || {};
        const primaryCat = (rec.categories && rec.categories[0]) || "places";
        const url = prettyItemUrl("https://bestmuscat.com/", primaryCat, entry.slug);
        return { "@type":"ListItem", "position": i+1, "url": url };
      })
    };
    elJSON.textContent = JSON.stringify(itemList);

  } catch (e) {
    console.warn(e);
    document.getElementById("c-grid").innerHTML =
      `<div class="empty">Couldn’t load curated list. Check <code>data/curations.json</code> and <code>data/tools.json</code>.</div>`;
  }
})();
