/* FILE: assets/app.js */
(function () {
  // ---------- CONFIG ----------
  const CONFIG = {
    GOOGLE_FORM_URL: "",
    ITEMS_PER_PAGE: 9,
    SITE_URL: "https://bestmuscat.com/",
    ASSET_VERSION: "1"
  };

  // ---------- CATEGORY DEFINITIONS ----------
  const CATEGORIES = [
    { name: "Hotels",      slug: "hotels" },
    { name: "Restaurants", slug: "restaurants" },
    { name: "Schools",     slug: "schools" },
    { name: "Spas",        slug: "spas" },
    { name: "Clinics",     slug: "clinics" },
    { name: "Malls",       slug: "malls" },
    // new (from scratch)
    { name: "Car Repair Garages",          slug: "car-repair-garages" },
    { name: "Home Maintenance and Repair", slug: "home-maintenance-and-repair" },
    { name: "Catering Services",           slug: "catering-services" },
    { name: "Events Planning",             slug: "events" },
    { name: "Moving and Storage",          slug: "moving-and-storage" }
  ];
  const CATEGORY_SLUG_SET = new Set(CATEGORIES.map(c => c.slug));

  // ---------- SEO HELPERS ----------
  function setMeta(name, content) {
    if (!content) return;
    let el = document.querySelector(`meta[name="${name}"]`);
    if (!el) { el = document.createElement("meta"); el.setAttribute("name", name); document.head.appendChild(el); }
    el.setAttribute("content", content);
  }
  function setOG(property, content) {
    if (!content) return;
    let el = document.querySelector(`meta[property="${property}"]`);
    if (!el) { el = document.createElement("meta"); el.setAttribute("property", property); document.head.appendChild(el); }
    el.setAttribute("content", content);
  }
  function setCanonical(url) {
    let link = document.querySelector('link[rel="canonical"]');
    if (!link) { link = document.createElement("link"); link.setAttribute("rel", "canonical"); document.head.appendChild(link); }
    link.setAttribute("href", url);
  }
  function addJSONLD(obj) {
    const s = document.createElement("script");
    s.type = "application/ld+json";
    s.text = JSON.stringify(obj);
    document.head.appendChild(s);
  }
  function slugify(s) {
    return (s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  }

  // ---------- STATE ----------
  let tools = [];
  let visible = [];
  let fuse = null;
  let selectedCategories = new Set();
  let currentPricing = "all";
  let currentQuery = "";
  let currentPage = 1;
  let forceBestThingsView = false; // special landing
  let toolsBySlug = {};

  // ---------- ELEMENTS ----------
  const elSearch     = document.getElementById("search");
  const elChips      = document.getElementById("chips");
  const elPricing    = document.getElementById("pricing");
  const elSuggest    = document.getElementById("suggest-link");
  const elCount      = document.getElementById("count");
  const elGrid       = document.getElementById("results");
  const elPagination = document.getElementById("pagination");
  const elPrev       = document.getElementById("prev");
  const elNext       = document.getElementById("next");
  const elPage       = document.getElementById("page");
  const elPageInfo   = document.getElementById("page-info");
  const elShowcase   = document.getElementById("showcase");
  const elShowMalls  = document.getElementById("showcase-malls");
  const elShowHotels = document.getElementById("showcase-hotels");
  const elShowRests  = document.getElementById("showcase-restaurants");
  const elShowSchools= document.getElementById("showcase-schools");
  const elShowGarages  = document.getElementById("showcase-garages");
  const elShowHome     = document.getElementById("showcase-home");
  const elShowCatering = document.getElementById("showcase-catering");
  const elShowEvents   = document.getElementById("showcase-events");
  const elShowMoving   = document.getElementById("showcase-moving");
  const elBack       = document.getElementById("bt-back");

  // ---------- UTIL ----------
  const qs = new URLSearchParams(location.search);
  function setQueryParam(key, val) {
    const url = new URL(location.href);
    if (val === null || val === undefined || val === "" || (Array.isArray(val) && val.length === 0)) {
      url.searchParams.delete(key);
    } else {
      url.searchParams.set(key, Array.isArray(val) ? val.join(",") : String(val));
    }
    history.replaceState({}, "", url.toString());
  }
  function getArrayParam(name) {
    const v = qs.get(name);
    return v ? v.split(",").map(s => s.trim()).filter(Boolean) : [];
  }
  function debounce(fn, ms=200) {
    let t=null;
    return (...args)=>{ clearTimeout(t); t=setTimeout(()=>fn(...args), ms); };
  }
  function esc(s){ return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  function ratingBadgeHTML(t){
    const raw = t?.rating_overall ?? t?.star_rating;
    const r = Number(raw);
    if (!isFinite(r)) return "";
    const rc = Number(t?.review_count);
    const rcHTML = isFinite(rc) && rc > 0 ? `<span class="rc">(${Math.round(rc).toLocaleString()})</span>` : "";
    const starSVG = `
      <svg class="star" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 17.27l6.18 3.73-1.64-7.03 5.46-4.73-7.19-.62L12 2 9.19 8.62l-7.19.62 5.46 4.73L5.82 21z"></path>
      </svg>`;
    return `<div class="rating-badge" title="Rating">
      ${starSVG}<span class="val">${r.toFixed(1)}</span>${rcHTML}
    </div>`;
  }
  function ratingChipHTML(t){
    const raw = t?.rating_overall ?? t?.star_rating ?? t?.rating;
    const r = Number(raw);
    if (!isFinite(r)) return "";
    const rc   = Number(t?.review_count);
    const src  = t?.review_source || "Google";
    const meta = [src, (isFinite(rc) && rc > 0) ? `${rc} reviews` : null].filter(Boolean).join(" · ");
    const starSVG = `
      <svg class="star" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 17.27l6.18 3.73-1.64-7.03 5.46-4.73-7.19-.62L12 2 9.19 8.62l-7.19.62 5.46 4.73L5.82 21z"></path>
      </svg>`;
    return `<span class="rating-chip">${starSVG}<span class="val">${r.toFixed(1)}</span>${meta ? `<span class="meta">${esc(meta)}</span>` : ""}</span>`;
  }

  function pricingBadge() { return ""; }
  function iconRow() { return ""; }

  function isValidUrl(u){
    try{ const x=new URL(u); return ['http:','https:'].includes(x.protocol); }catch{ return false; }
  }
  function isExampleDomain(u){
    try{ return /(^|\.)example\.com$/i.test(new URL(u).hostname); }catch{ return false; }
  }

  // image helpers
  function isRemoteUrl(u) { return /^https?:\/\//i.test(String(u || "")); }
  function looksLikeLogo(u) {
    return /(?:^|\/)(?:logo|logos?|brand|mark|icon|icons?|favicon|sprite|social)(?:[-_./]|$)/i.test(u || "") || /\.svg(?:$|\?)/i.test(u || "");
  }
  function pickCardImage(obj) {
    const candidates = [obj.image, obj.hero, obj.photo, obj.images && obj.images.card, obj.images && obj.images.hero].filter(Boolean);
    for (const c of candidates) { if (!isRemoteUrl(c)) return c; }
    const remote = obj.hero_url || (obj.images && obj.images.hero) || obj.image || obj.logo_url;
    if (remote && isRemoteUrl(remote) && !looksLikeLogo(remote)) return remote;
    return "";
  }

  // favicon fallback helpers (unchanged)
  function hostnameFromUrl(u) { try { return new URL(u).hostname; } catch { return ""; } }
  function installLogoErrorFallback() {
    document.querySelectorAll('img.logo[data-domain]').forEach(img => {
      if (img.dataset._wired) return;
      img.dataset._wired = "1";
      img.addEventListener('error', () => {
        const domain = img.dataset.domain;
        if (!domain) {
          const name = img.getAttribute('alt')?.replace(/ logo$/i, '') || 'AI';
          const div = document.createElement('div');
          div.className = 'logo';
          div.setAttribute('aria-hidden', 'true');
          div.textContent = (name.split(/\s+/).slice(0,2).map(s=>s[0]?.toUpperCase()||'').join('')) || 'AI';
          img.replaceWith(div);
          return;
        }
        if (!img.dataset.triedHorse) { img.dataset.triedHorse = "1"; img.src = `https://icon.horse/icon/${encodeURIComponent(domain)}`; return; }
        if (!img.dataset.triedS2)    { img.dataset.triedS2    = "1"; img.src = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`; return; }
        const name = img.getAttribute('alt')?.replace(/ logo$/i, '') || 'AI';
        const div = document.createElement('div');
        div.className = 'logo';
        div.setAttribute('aria-hidden', 'true');
        div.textContent = (name.split(/\s+/).slice(0,2).map(s=>s[0]?.toUpperCase()||'').join('')) || 'AI';
        img.replaceWith(div);
      }, { once: false });
    });
  }

  // ----- PAGINATION HELPERS -----
  function getPageWindow(curr, total, width = 5) {
    const half = Math.floor(width / 2);
    let start = Math.max(1, curr - half);
    let end = Math.min(total, start + width - 1);
    start = Math.max(1, end - width + 1);
    return { start, end };
  }
  function ensurePagerNumbersContainer() {
    let el = elPagination.querySelector('.pager-numbers');
    if (!el) {
      el = document.createElement('div');
      el.className = 'pager-numbers';
      elPagination.insertBefore(el, elNext);
    }
    return el;
  }
  function renderPaginationNumbers(totalPages) {
    const container = ensurePagerNumbersContainer();
    if (totalPages <= 1) { container.innerHTML = ''; return; }
    const { start, end } = getPageWindow(currentPage, totalPages, 5);
    let html = '';
    if (start > 1) {
      html += `<button class="page-btn" data-page="1" aria-label="Go to page 1">1</button>`;
      if (start > 2) html += `<span class="dots" aria-hidden="true">…</span>`;
    }
    for (let p = start; p <= end; p++) {
      const active = p === currentPage ? ' active' : '';
      const ariaCur = p === currentPage ? ` aria-current="page"` : '';
      html += `<button class="page-btn${active}" data-page="${p}"${ariaCur} aria-label="Go to page ${p}">${p}</button>`;
    }
    if (end < totalPages) {
      if (end < totalPages - 1) html += `<span class="dots" aria-hidden="true">…</span>`;
      html += `<button class="page-btn" data-page="${totalPages}" aria-label="Go to page ${totalPages}">${totalPages}</button>`;
    }
    container.innerHTML = html;
  }

  // ---------- CHIPS ----------
  function renderChips() {
    elChips.innerHTML = CATEGORIES.map(cat => {
      const pressed = selectedCategories.has(cat.slug);
      return `<button class="chip" type="button" data-slug="${esc(cat.slug)}" aria-pressed="${pressed}">${esc(cat.name)}</button>`;
    }).join("");
    updateChipsActive();
  }
  function updateChipsActive() {
    elChips.querySelectorAll(".chip").forEach(btn => {
      const slug = btn.getAttribute("data-slug");
      const on   = selectedCategories.has(slug);
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  function updateChipCounts(countsBySlug) {
    elChips.querySelectorAll(".chip").forEach(btn => {
      const slug = btn.getAttribute("data-slug");
      const catName = (CATEGORIES.find(c => c.slug === slug) || {}).name || slug;
      const n = countsBySlug[slug] || 0;
      btn.innerHTML = `${esc(catName)} <span class="chip-count">${n}</span>`;
    });
  }

  // ---------- FETCH & INIT ----------
  async function init() {
    // Handle tool.html SEO and exit
    if (/tool\.html$/i.test(location.pathname)) {
      try {
        const slug = (new URLSearchParams(location.search)).get("slug") || "";
        const res = await fetch("data/tools.json?ts=" + Date.now(), { cache: "no-store" });
        if (!res.ok) throw new Error("tools.json not found");
        const data = await res.json();
        if (!Array.isArray(data)) throw new Error("tools.json must be an array");
        const normalized = data.map(t => ({
          id: t.id || t.slug || Math.random().toString(36).slice(2),
          slug: (t.slug || (t.name||"").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g,"")).slice(0,128),
          name: t.name || "Untitled",
          url: t.url || "#",
          tagline: t.tagline || "",
          description: t.description || "",
          pricing: ["free","freemium","paid"].includes(t.pricing) ? t.pricing : "freemium",
          categories: Array.isArray(t.categories) ? t.categories.filter(Boolean) : [],
          tags: Array.isArray(t.tags) ? t.tags.filter(Boolean) : [],
          logo: t.logo || "",
          image: t.image || "",
          short_description: t.short_description || t.tagline || "",
          price: t.price || t.pricing || ""
        }));
        const tool = normalized.find(t => t.slug === slug);
        if (!tool) {
          document.title = "Tool not found — Academia with AI";
          setMeta("description", "This tool could not be found.");
          setCanonical(`${CONFIG.SITE_URL}tool.html`);
          return;
        }
        const siteUrl = (CONFIG.SITE_URL || (location.origin + "/")).replace(/\/$/, "/");
        const primaryCat = (tool.categories && tool.categories[0]) || "places";
        const prettyUrl = (window.SEO_ROUTES && SEO_ROUTES.prettyItemUrl)
          ? SEO_ROUTES.prettyItemUrl(siteUrl, primaryCat, tool.slug)
          : `${siteUrl}tool.html?slug=${encodeURIComponent(tool.slug)}`;
        document.title = `${tool.name} — ${primaryCat} | Best Muscat`;
        setMeta("description", tool.short_description || `Discover ${tool.name} in Muscat.`);
        setCanonical(prettyUrl);
        setOG("og:title", document.title);
        setOG("og:description", tool.short_description || `Discover ${tool.name}.`);
        setOG("og:url", prettyUrl);
        setMeta("twitter:title", document.title);
        setMeta("twitter:description", tool.short_description || `Discover ${tool.name}.`);
        const defaultSocial = `${siteUrl}assets/og-default.jpg`;
        if (tool.image && /^https?:/i.test(tool.image)) {
          setOG("og:image", tool.image);
          setMeta("twitter:image", tool.image);
        } else {
          setOG("og:image", defaultSocial);
          setMeta("twitter:image", defaultSocial);
        }
        document.querySelector('meta[name="twitter:title"]')?.setAttribute('content', document.title);
        document.querySelector('meta[name="twitter:description"]')?.setAttribute('content', tool.short_description || `Discover ${tool.name}.`);
        document.querySelector('meta[name="twitter:image"]')?.setAttribute('content', (tool.image && /^https?:/i.test(tool.image)) ? tool.image : defaultSocial);
        addJSONLD({
          "@context": "https://schema.org",
          "@type": "SoftwareApplication",
          "name": tool.name,
          "url": prettyUrl,
          "operatingSystem": "Any",
          "applicationCategory": "EducationalApplication",
          "description": tool.short_description || undefined,
          "offers": (tool.price && String(tool.price).toLowerCase().includes("free"))
            ? { "@type": "Offer", "price": "0", "priceCurrency": "USD" }
            : undefined
        });
        const catSlug = slugify(primaryCat);
        const prettyCatUrl = (window.SEO_ROUTES && SEO_ROUTES.prettyCategoryUrl)
          ? SEO_ROUTES.prettyCategoryUrl(siteUrl, catSlug)
          : `${siteUrl}index.html?category=${encodeURIComponent(catSlug)}`;
        addJSONLD({
          "@context": "https://schema.org",
          "@type": "BreadcrumbList",
          "itemListElement": [
            { "@type": "ListItem", "position": 1, "name": "Home", "item": siteUrl },
            { "@type": "ListItem", "position": 2, "name": primaryCat, "item": prettyCatUrl },
            { "@type": "ListItem", "position": 3, "name": tool.name, "item": prettyUrl }
          ]
        });
      } catch (e) {
        console.warn("tool.html SEO init failed:", e);
      }
      return;
    }

    // Suggest form
    if (elSuggest && CONFIG.GOOGLE_FORM_URL) elSuggest.href = CONFIG.GOOGLE_FORM_URL;

    // Preselect chips from URL
    const startSelected = getArrayParam("category").filter(slug=>CATEGORY_SLUG_SET.has(slug));
    startSelected.forEach(s=>selectedCategories.add(s));
    renderChips();

    // Chip clicks
    elChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn || !elChips.contains(btn)) return;
      const slug = btn.getAttribute("data-slug");
      if (!CATEGORY_SLUG_SET.has(slug)) return;

      if (selectedCategories.has(slug)) selectedCategories.delete(slug);
      else selectedCategories.add(slug);

      currentPage = 1;
      setQueryParam("category", Array.from(selectedCategories));

      // FIX: exit special landing and clear q
      forceBestThingsView = false;
      setQueryParam("q", "");
      currentQuery = "";
      if (elSearch) elSearch.value = "";

      // Unhide UI just in case
      const toolbar = document.querySelector(".toolbar");
      if (toolbar) toolbar.style.display = "";
      if (elChips)      elChips.style.display      = "";
      if (elCount)      elCount.style.display      = "";
      if (elGrid)       elGrid.style.display       = "";
      if (elPagination) elPagination.style.display = "";
      if (elPageInfo && elPageInfo.parentElement) elPageInfo.parentElement.style.display = "";
      if (elShowcase) elShowcase.style.display = selectedCategories.size === 0 && !currentQuery ? "" : "none";

      updateChipsActive();
      applyFilters();
    });

    // Search from URL
    const q = qs.get("q") || "";
    currentQuery = q;
    if (elSearch) elSearch.value = q;

    // Special landing only if NO category present
    const hasCategoryParam = getArrayParam("category").length > 0;
    const isBestThingsLanding = ((q || "").trim().toLowerCase() === "best things to do") && !hasCategoryParam;
    if (isBestThingsLanding) {
      forceBestThingsView = true;
      currentQuery = "";
      if (elSearch) elSearch.value = "";
      if (elBack) elBack.hidden = false;
      const toolbar = document.querySelector(".toolbar");
      if (toolbar) toolbar.style.display = "none";
      if (elChips)      elChips.style.display      = "none";
      if (elCount)      elCount.style.display      = "none";
      if (elGrid)       elGrid.style.display       = "none";
      if (elPagination) elPagination.style.display = "none";
      if (elPageInfo && elPageInfo.parentElement) elPageInfo.parentElement.style.display = "none";
      if (elShowcase) elShowcase.style.display = "none";
      document.getElementById('clear-filters')?.remove();
    }

    // Page from URL
    const pageParam = parseInt(qs.get("page") || "1", 10);
    currentPage = Number.isFinite(pageParam) && pageParam>0 ? pageParam : 1;

    // Load tools
    let data = [];
    try {
      const res = await fetch("data/tools.json?ts=" + Date.now(), { cache: "no-store" });
      if (!res.ok) throw new Error("tools.json not found");
      data = await res.json();
      if (!Array.isArray(data)) throw new Error("tools.json must be an array");
      toolsBySlug = Object.fromEntries((data || []).map(p => [p.slug, p]));
    } catch (err) {
      console.warn(err);
      if (elGrid) elGrid.innerHTML = `<div class="empty">Could not load <code>data/tools.json</code>.</div>`;
      if (elCount) elCount.textContent = "";
      if (elPagination) elPagination.hidden = true;
      return;
    }

    // Also support ?cat=...
    const selectedCatSlug = slugify(qs.get("cat") || "");
    if (selectedCatSlug) selectedCategories.add(selectedCatSlug);

    tools = data.map(t => ({
      id: t.id || t.slug || Math.random().toString(36).slice(2),
      slug: (t.slug || (t.name||"").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g,"")).slice(0,128),
      name: t.name || "Untitled",
      url: t.url || "#",
      tagline: t.tagline || "",
      description: t.description || "",
      pricing: ["free","freemium","paid"].includes(t.pricing) ? t.pricing : "freemium",
      categories: Array.isArray(t.categories) ? t.categories.filter(Boolean) : [],
      tags: Array.isArray(t.tags) ? t.tags.filter(Boolean) : [],
      logo: t.logo || "",
      image: t.image || t.hero || t.photo || t.hero_url || t.logo || t.logo_url ||
             (t.images && (t.images.hero || t.images.logo)) || "",
      evidence_cites: Boolean(t.evidence_cites),
      local_onprem: Boolean(t.local_onprem),
      edu_discount: Boolean(t.edu_discount),
      free_tier: "free"===t.pricing || Boolean(t.free_tier),
      beta: Boolean(t.beta),
      created_at: t.created_at || new Date().toISOString().slice(0,10)
    }));

    // Showcases
    function renderShowcases() {
      const pick = (slug) => tools
        .filter(t => (t.categories || []).some(c => slugify(c) === slug || c === slug))
        .slice(0, 6);
      const renderInto = (el, items) => { if (el) el.innerHTML = items.map(cardHTML).join(""); };
      renderInto(elShowMalls,   pick('malls'));
      renderInto(elShowHotels,  pick('hotels'));
      renderInto(elShowRests,   pick('restaurants'));
      renderInto(elShowSchools, pick('schools'));
      renderInto(elShowGarages,  pick('car-repair-garages'));
      renderInto(elShowHome,     pick('home-maintenance-and-repair'));
      renderInto(elShowCatering, pick('catering-services'));
      renderInto(elShowEvents,   pick('events'));
      renderInto(elShowMoving,   pick('moving-and-storage'));
    }
    renderShowcases();

    // Fuse
    fuse = new Fuse(tools, { includeScore: true, threshold: 0.35, ignoreLocation: true, keys: ["name", "tagline", "description", "tags"] });

    // Search input
    elSearch?.addEventListener("input", debounce((e)=>{
      currentQuery = e.target.value.trim();
      currentPage = 1;
      setQueryParam("q", currentQuery || null);
      applyFilters();
    }, 180));

    // Pager buttons
    elPrev?.addEventListener("click", ()=>{ if (currentPage>1){ currentPage--; setQueryParam("page", currentPage); render(); } });
    elNext?.addEventListener("click", ()=>{ const totalPages = Math.max(1, Math.ceil(visible.length / CONFIG.ITEMS_PER_PAGE)); if (currentPage<totalPages){ currentPage++; setQueryParam("page", currentPage); render(); } });

    elPagination?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-page]');
      if (!btn || !elPagination.contains(btn)) return;
      const p = parseInt(btn.dataset.page, 10);
      if (!Number.isFinite(p) || p === currentPage) return;
      currentPage = p;
      setQueryParam('page', currentPage);
      render();
    });

    // Clear filters (skip on landing)
    if (!forceBestThingsView) {
      let elClear = document.getElementById('clear-filters');
      if (!elClear) {
        elClear = document.createElement('button');
        elClear.id = 'clear-filters';
        elClear.type = 'button';
        elClear.className = 'chip';
        elClear.title = 'Reset search, pricing, and categories';
        elClear.textContent = 'Clear filters';
        if (elChips && elChips.parentNode) elChips.parentNode.insertBefore(elClear, elChips.nextSibling);
        else document.body.appendChild(elClear);
      }
      elClear.addEventListener('click', () => {
        selectedCategories.clear();
        currentQuery = '';
        currentPage = 1;
        if (elSearch) elSearch.value = '';
        setQueryParam('category', null);
        setQueryParam('q', null);
        setQueryParam('page', 1);
        updateChipsActive();
        applyFilters();
      });
    } else {
      document.getElementById('clear-filters')?.remove();
    }

    applyFilters(true);
  }

  // ---------- JSON-LD helpers ----------
  function injectItemListJSONLD() {
    // Create the script tag once; updateItemListJSONLD will populate it
    let el = document.getElementById("jsonld-list");
    if (!el) {
      el = document.createElement("script");
      el.type = "application/ld+json";
      el.id = "jsonld-list";
      document.head.appendChild(el);
    }
  }
  function updateItemListJSONLD(items) {
    const el = document.getElementById("jsonld-list");
    if (!el) return;
    const obj = {
      "@context": "https://schema.org",
      "@type": "ItemList",
      "itemListElement": items.map((t, i) => {
        const primaryCat = (t.categories && t.categories[0]) || "places";
        const pretty = (window.SEO_ROUTES && SEO_ROUTES.prettyItemUrl)
          ? SEO_ROUTES.prettyItemUrl((CONFIG.SITE_URL || (location.origin + "/")), primaryCat, t.slug)
          : ((CONFIG.SITE_URL || (location.origin + "/")).replace(/\/$/, "/") + `tool.html?slug=${encodeURIComponent(t.slug)}`);
        return { "@type": "ListItem", "position": i + 1, "url": pretty };
      })
    };
    el.textContent = JSON.stringify(obj);
  }

  // ---------- FILTERING ----------
  function applyFilters(first=false) {
    if (forceBestThingsView) {
      if (elShowcase) elShowcase.style.display = "none";
      if (elGrid)       elGrid.style.display       = "none";
      if (elPagination) elPagination.style.display = "none";
      if (elCount)      elCount.style.display      = "none";
      if (elPageInfo && elPageInfo.parentElement) elPageInfo.parentElement.style.display = "none";
      return;
    }

    const catFilter = Array.from(selectedCategories);
    let arr = tools.slice();

    if (catFilter.length > 0) {
      arr = arr.filter(t => t.categories.some(c => catFilter.includes(slugify(c)) || catFilter.includes(c)));
    }
    if (catFilter.length > 0 && arr.length === 0) arr = tools.slice();

    if (currentQuery) {
      const results = fuse.search(currentQuery);
      arr = results.map(r => r.item);
    }

    // counts for chips
    let pool = tools.slice();
    if (currentQuery) {
      const poolResults = new Set(fuse.search(currentQuery).map(r => r.item));
      pool = pool.filter(t => poolResults.has(t));
    }
    const countsBySlug = {};
    for (const t of pool) {
      for (const c of (t.categories || [])) {
        const slug = CATEGORY_SLUG_SET.has(c) ? c : slugify(c);
        countsBySlug[slug] = (countsBySlug[slug] || 0) + 1;
      }
    }
    updateChipCounts(countsBySlug);

    const isHome = (selectedCategories.size === 0) && !currentQuery;
    if (elShowcase) elShowcase.style.display = isHome ? "" : "none";
    const elVisit = document.getElementById('visit-muscat');
    if (elVisit) elVisit.style.display = isHome ? "" : "none";
    if (elGrid)       elGrid.style.display       = isHome ? "none" : "";
    if (elPagination) elPagination.style.display = isHome ? "none" : "";
    if (elCount)      elCount.style.display      = isHome ? "none" : "";
    if (elPageInfo && elPageInfo.parentElement) elPageInfo.parentElement.style.display = isHome ? "none" : "";

    visible = arr;
    if (first) injectItemListJSONLD();
    render();
  }

  // ---------- RENDER ----------
  function render() {
    const total = visible.length;
    if (elCount) elCount.textContent = total ? `${total} tool${total===1?"":"s"} found` : "No matching tools found.";
    if (elPageInfo) elPageInfo.textContent = `Showing ${Math.min(total, ((currentPage-1)*CONFIG.ITEMS_PER_PAGE)+1)}–${Math.min(total, currentPage*CONFIG.ITEMS_PER_PAGE)} of ${total}`;

    const totalPages = Math.max(1, Math.ceil(total / CONFIG.ITEMS_PER_PAGE));
    currentPage = Math.min(currentPage, totalPages);
    if (elPrev) elPrev.disabled = currentPage<=1;
    if (elNext) elNext.disabled = currentPage>=totalPages;
    if (elPage) elPage.textContent = `Page ${currentPage} of ${totalPages}`;
    if (elPagination) elPagination.hidden = total<=CONFIG.ITEMS_PER_PAGE;

    renderPaginationNumbers(totalPages);

    const start = (currentPage-1) * CONFIG.ITEMS_PER_PAGE;
    const pageItems = visible.slice(start, start + CONFIG.ITEMS_PER_PAGE);

    if (elGrid) elGrid.innerHTML = pageItems.map(cardHTML).join("");
    installLogoErrorFallback();

    const og = document.getElementById("og-url");
    if (og) og.setAttribute("content", CONFIG.SITE_URL);

    updateItemListJSONLD(pageItems.slice(0,10));
  }

  function cardHTML(t) {
    const primaryCat = (t.categories && t.categories[0]) || "places";
    const detailUrl = (window.SEO_ROUTES && SEO_ROUTES.prettyItemUrl)
      ? SEO_ROUTES.prettyItemUrl((CONFIG.SITE_URL || (location.origin + "/")), primaryCat, t.slug)
      : `tool.html?slug=${encodeURIComponent(t.slug)}`;

    const src = toolsBySlug[t.slug] || t;
    const title    = esc(t.name);
    const subtitle = esc(t.tagline || t.description.slice(0, 120) || "");
    const cats     = (t.categories || []).slice(0,2).map(c=>`<span class="badge">${esc(c)}</span>`).join(" ");
    const tagChips = (t.tags || []).slice(0,5).map(c=>`<span class="tag">${esc(c)}</span>`).join(" ");

    const websiteRaw = src.website || src.url || "";
    const mapsUrl    = (src.maps_url && String(src.maps_url).startsWith('https://www.google.com/maps/')) ? src.maps_url : "";
    const hasRealWebsite = isValidUrl(websiteRaw) && !isExampleDomain(websiteRaw);

    const ctas = [];
    if (hasRealWebsite) {
      ctas.push(`<a class="link-btn" href="${esc(websiteRaw)}" target="_blank" rel="noopener" aria-label="Visit ${title} website">Website</a>`);
    } else if (mapsUrl) {
      ctas.push(`<a class="link-btn" href="${esc(mapsUrl)}" target="_blank" rel="noopener" aria-label="Open ${title} on Google Maps">Google Maps</a>`);
    }
    ctas.push(`<a class="link-btn" href="${detailUrl}" aria-label="View ${title} details">View</a>`);

    const imgSrc = pickCardImage(src);
    const badge = ratingBadgeHTML(t);
    const topImage = imgSrc
      ? `
        <a href="${detailUrl}" class="card-img" aria-label="${title} details">
          <img
            src="${esc(imgSrc)}"
            alt="${title}"
            loading="lazy"
            decoding="async"
            onerror="
              const wrap = this.closest('.card-img');
              if (wrap) {
                wrap.classList.add('img-fallback');
                wrap.innerHTML = '<div class=&quot;img-placeholder&quot;>${esc((t.name||'').split(/\\s+/).slice(0,2).map(s=>s[0]?.toUpperCase()||'').join('')||'BM')}</div>';
              }
            "
          />
          ${badge}
        </a>`
      : `
        <a href="${detailUrl}" class="card-img img-fallback" aria-label="${title} details">
          <div class="img-placeholder">${esc((t.name||'').split(/\s+/).slice(0,2).map(s=>s[0]?.toUpperCase()||'').join('')||'BM')}</div>
          ${badge}
        </a>`;

    return `
      <article class="card card--place">
        ${topImage}
        <div class="card-body">
          <h2 class="card-title"><a href="${detailUrl}" title="${title}" class="card-link">${title}</a></h2>
          <p class="card-sub">${subtitle}</p>
          <div class="badges">${cats}</div>
          <div class="tags">${tagChips}</div>
          <div class="ctas">${ctas.join(" ")} ${ratingChipHTML(src)}</div>
        </div>
      </article>
    `;
  }

  // ---- Best Things to Do renderer (assets/best-things.json) ----
  // Assumes: toolsBySlug (lookup by slug), tools (array), SEO_ROUTES.prettyItemUrl, CONFIG.SITE_URL,
  // and helpers: slugify, esc, isValidUrl, isExampleDomain, pickCardImage (optional).
  
  async function renderBestThings(opts = {}) {
    const grid = document.getElementById(opts.containerId || "best-things-grid");
    if (!grid) return; // nothing to do
  
    // 1) Load best-things.json
    let items = [];
    try {
      const res = await fetch("assets/best-things.json?ts=" + Date.now(), { cache: "no-store" });
      if (!res.ok) throw new Error("best-things.json not found");
      items = await res.json();
      if (!Array.isArray(items)) throw new Error("best-things.json must be an array");
    } catch (e) {
      console.warn("Failed to load best-things.json:", e);
      grid.innerHTML = `<div class="empty">Could not load <code>assets/best-things.json</code>.</div>`;
      return;
    }
  
    // 2) Try to find a matching tools entry for “View” detail pages
    // Strategy: best match by slug (if present in tools), else by normalized title.
    // If none found, "View" falls back to item.url (website/maps).
    const toolsByTitle = {};
    (Array.isArray(tools) ? tools : []).forEach(t => {
      const key = (t.name || "").trim().toLowerCase();
      if (key) toolsByTitle[key] = t;
    });
  
    function findMatchingTool(item) {
      // If best-things.json ever includes "slug", we prefer that:
      if (item.slug && toolsBySlug[item.slug]) return toolsBySlug[item.slug];
  
      // Otherwise try title match
      const key = (item.title || "").trim().toLowerCase();
      return toolsByTitle[key] || null;
    }
  
    function prettyDetailUrl(tool) {
      if (!tool) return "";
      const siteUrl = (CONFIG.SITE_URL || (location.origin + "/"));
      const primaryCat = (tool.categories && tool.categories[0]) || "places";
      if (window.SEO_ROUTES && SEO_ROUTES.prettyItemUrl) {
        return SEO_ROUTES.prettyItemUrl(siteUrl, primaryCat, tool.slug);
      }
      return `tool.html?slug=${encodeURIComponent(tool.slug)}`;
    }
  
    function chooseCtaUrl(item) {
      // Prefer a real website; else a maps URL already in the item
      const u = item.url || "";
      if (isValidUrl(u) && !isExampleDomain(u)) return u;
      return u; // may be a Google Maps place link already
    }
  
    function cardHTMLforBestThing(item) {
      const matchedTool = findMatchingTool(item);
      const viewHref = matchedTool ? prettyDetailUrl(matchedTool) : (chooseCtaUrl(item) || "#");
  
      // If you want a nicer image, you can try to use matched tool’s hero image:
      let img = item.image_url || "";
      if ((!img || /\.svg(?:$|\?)/i.test(img) || /(^|\/)(logo|icon|favicon|social)/i.test(img)) && matchedTool) {
        const fallback = pickCardImage(matchedTool);
        if (fallback) img = fallback;
      }
  
      const title = esc(item.title || "");
      const subtitle = esc(item.subtitle || item.title || "");
      const tags = Array.isArray(item.tags) ? item.tags.slice(0, 5) : [];
      const tagsHTML = tags.map(t => `<span class="tag">${esc(t)}</span>`).join(" ");
  
      const learnHref = chooseCtaUrl(item);
      const learnLabel = esc(item.cta_label || "Learn More");
  
      const imageHTML = img
        ? `<a href="${esc(viewHref)}" class="card-img" aria-label="${title} details">
             <img src="${esc(img)}" alt="${title}" loading="lazy" decoding="async" />
           </a>`
        : `<a href="${esc(viewHref)}" class="card-img img-fallback" aria-label="${title} details">
             <div class="img-placeholder">${esc((item.title||'').split(/\s+/).slice(0,2).map(s=>s[0]?.toUpperCase()||'').join('')||'BM')}</div>
           </a>`;
  
      const ctas = [
        learnHref ? `<a class="link-btn" href="${esc(learnHref)}" target="_blank" rel="noopener">${learnLabel}</a>` : "",
        `<a class="link-btn" href="${esc(viewHref)}" aria-label="View ${title} details">View</a>`
      ].filter(Boolean).join(" ");
  
      return `
        <article class="card card--place">
          ${imageHTML}
          <div class="card-body">
            <h2 class="card-title"><a href="${esc(viewHref)}" class="card-link">${title}</a></h2>
            <p class="card-sub">${subtitle}</p>
            <div class="tags">${tagsHTML}</div>
            <div class="ctas">${ctas}</div>
          </div>
        </article>
      `;
    }
  
    // Optional: order by category A→Z, then priority asc (if present)
    items.sort((a, b) => {
      const ca = (a.category || "").toLowerCase();
      const cb = (b.category || "").toLowerCase();
      if (ca !== cb) return ca < cb ? -1 : 1;
      const pa = Number.isFinite(+a.priority) ? +a.priority : 9999;
      const pb = Number.isFinite(+b.priority) ? +b.priority : 9999;
      return pa - pb;
    });
  
    grid.innerHTML = items.map(cardHTMLforBestThing).join("");
  }

  // ---------- START ----------
  if (document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
