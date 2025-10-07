// FILE: assets/curated.js
(async function () {
  const qs = new URLSearchParams(location.search);
  const listSlug = qs.get("list") || "";

  const elTitle = document.getElementById("c-title");
  const elIntro = document.getElementById("c-intro");
  const elGrid  = document.getElementById("c-grid");
  const elJSON  = document.getElementById("jsonld-list");

  // --- small utils ---
  function esc(s){ return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function initials(name) {
    return (name||"").split(/\s+/).slice(0,2).map(p=>p[0]?.toUpperCase()||"").join("") || "BM";
  }
  const siteUrl = (location.origin + "/").replace(/\/$/, "/");

  // Prefer your SEO route helper if present (assets/seo-routes.js), else fallback
  function prettyItemUrl(primaryCat, slug) {
    if (window.SEO_ROUTES && typeof SEO_ROUTES.prettyItemUrl === "function") {
      return SEO_ROUTES.prettyItemUrl(siteUrl, primaryCat, slug);
    }
    return `${siteUrl}${encodeURIComponent(primaryCat)}/${encodeURIComponent(slug)}/`;
  }

  // --- image picking (mirrors app.js behavior, but simplified) ---
  function isRemoteUrl(u){ return /^https?:\/\//i.test(String(u||"")); }
  function looksLikeLogo(u){
    return /(?:^|\/)(?:logo|logos?|brand|mark|icon|icons?|favicon|sprite|social)(?:[-_./]|$)/i.test(u||"") || /\.svg(?:$|\?)/i.test(u||"");
  }
  function pickCardImage(obj){
    const candidates = [
      obj.image, obj.hero, obj.photo,
      obj.images && obj.images.card,
      obj.images && obj.images.hero
    ].filter(Boolean);

    // prefer local paths
    for (const c of candidates) {
      if (!isRemoteUrl(c)) return c;
    }

    // allow safe remote (avoid logos)
    const remote = obj.hero_url || (obj.images && obj.images.hero) || obj.image || obj.logo_url;
    if (remote && isRemoteUrl(remote) && !looksLikeLogo(remote)) return remote;

    return ""; // none
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

    // --- Page head/meta ---
    const pageUrl = new URL(location.href);
    pageUrl.search = `?list=${encodeURIComponent(curation.slug)}`;

    document.title = `${curation.title} — Best Muscat`;
    elTitle.textContent = curation.title || "Curated List";
    elIntro.textContent = curation.intro || "";

    // update meta (only if the IDs exist in list.html)
    document.getElementById("doc-title")?.textContent = document.title;
    document.getElementById("canonical")?.setAttribute("href", pageUrl.toString());
    document.getElementById("meta-desc")?.setAttribute("content", curation.intro || "Hand-picked highlights across Muscat.");
    document.getElementById("og-title")?.setAttribute("content", curation.title || "Curated List");
    document.getElementById("og-url")?.setAttribute("content", pageUrl.toString());

    // --- Build cards in curated order ---
    const itemsHTML = (curation.items || []).map(entry => {
      const rec = bySlug[entry.slug] || {};
      const primaryCat = (rec.categories && rec.categories[0]) || "places";
      const detailUrl = prettyItemUrl(primaryCat, entry.slug);
      const title = esc(rec.name || entry.slug);
      const subtitle = esc(rec.tagline || rec.short_description || rec.description || "");
      const tags = (rec.tags || []).slice(0,5).map(t=>`<span class="tag">${esc(t)}</span>`).join("");

      const hero = pickCardImage(rec);
      const imgHtml = hero
        ? `
          <a href="${detailUrl}" class="card-img" aria-label="${title} details">
            <img
              src="${esc(hero)}"
              alt="${title}"
              loading="lazy"
              decoding="async"
              onerror="
                const wrap = this.closest('.card-img');
                if (wrap) { wrap.classList.add('img-fallback'); wrap.innerHTML = '<div class=&quot;img-placeholder&quot;>${esc(initials(rec.name||entry.slug))}</div>'; }
              "
            />
          </a>`
        : `
          <a href="${detailUrl}" class="card-img img-fallback" aria-label="${title} details">
            <div class="img-placeholder">${esc(initials(rec.name||entry.slug))}</div>
          </a>`;

      const sponsored = entry.sponsored ? `<span class="badge" title="Paid placement">Sponsored</span>` : "";

      // Website CTA if real
      const website = rec.website || rec.url || "";
      const websiteIsReal = (() => {
        try {
          const u = new URL(website);
          return /^(https?:)$/.test(u.protocol) && !/(\.|^)example\.com$/i.test(u.hostname);
        } catch { return false; }
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

    elGrid.innerHTML = itemsHTML.join("");

    // --- JSON-LD ItemList for the curated page ---
    const itemList = {
      "@context": "https://schema.org",
      "@type": "ItemList",
      "name": curation.title,
      "itemListElement": (curation.items || []).map((entry, i) => {
        const rec = bySlug[entry.slug] || {};
        const primaryCat = (rec.categories && rec.categories[0]) || "places";
        const url = prettyItemUrl(primaryCat, entry.slug);
        return { "@type":"ListItem", "position": i+1, "url": url };
      })
    };
    elJSON.textContent = JSON.stringify(itemList);

  } catch (e) {
    console.warn(e);
    elGrid.innerHTML =
      `<div class="empty">Couldn’t load curated list. Check <code>data/curations.json</code> and <code>data/tools.json</code>.</div>`;
  }
})();
