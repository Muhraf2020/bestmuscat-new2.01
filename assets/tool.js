(function(){
  const qs = new URLSearchParams(location.search);
  const slug = (qs.get("slug") || "").trim().toLowerCase();

  const el = {
    title:   document.getElementById("d-title"),
    rating:  document.getElementById("d-rating"),
    open:    document.getElementById("d-open"),
    price:   document.getElementById("d-price"),
    cat:     document.getElementById("d-category"),
    about:   document.getElementById("d-about"),
    hero:    document.getElementById("d-hero"),
    btnShare:document.getElementById("btn-share"),
    btnVisit:document.getElementById("btn-visit"),
    btnCall: document.getElementById("btn-call"),
    btnMaps: document.getElementById("btn-maps"),
    hours:   document.getElementById("d-hours"),
    loc:     document.getElementById("d-location"),
    aside:   document.getElementById("d-details"),
    scores:  document.getElementById("d-scores"),
    relatedGrid: document.getElementById("related-grid"),
    verify:  document.getElementById("d-verify"),
  };

  // ─────────────────────────────────────────────────────────────────────────────
  // Helpers
  function esc(s){ return String(s||""); }
  function slugify(s){ return (s||"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,""); }
  function titleCase(s){ return String(s||"").replace(/_/g," ").replace(/\b\w/g, m => m.toUpperCase()); }
  function numberOrDash(v, digits=2){ return (typeof v === "number" && isFinite(v)) ? v.toFixed(digits) : "—"; }
  function hideCard(id){ document.getElementById(id)?.setAttribute('hidden',''); }
  function showCard(id){ document.getElementById(id)?.removeAttribute('hidden'); }

  // Data-driven visibility helpers
  function hasSchema(item, cols = []) {
    const keys = Array.isArray(item.schema_keys) ? item.schema_keys : [];
    return cols.some(c => keys.includes(c)); // CSV has ANY of these columns
  }
  function hasData(item, cols = [], extraChecks = []) {
    const valHit = cols.some(c => {
      const v = item[c];
      return Array.isArray(v) ? v.length > 0 : (v !== undefined && v !== null && String(v).trim() !== "");
    });
    const extraHit = extraChecks.some(fn => { try { return !!fn(item); } catch { return false; } });
    return valHit || extraHit;
  }

  // One-time mapping from UI sections → relevant CSV columns
  const FEATURE_REQUIREMENTS = {
    about:     { cols: ["about_short","about_long","description","tagline"] },
    amenities: { cols: ["amenities"] },
    cuisines:  { cols: ["cuisines"] },
    meals:     { cols: ["meals"] },
    rating:    { cols: ["rating_overall","sub_food_quality","sub_service","sub_ambience","sub_value","sub_accessibility","subscores","scores","public_sentiment"] },
    hours:     { cols: ["hours_raw"] }, // parsed into item.hours
    map:       { cols: ["address","lat","lng","maps_url"] },
    details:   { cols: ["categories","tags","pricing","price_range","neighborhood","city","country","lat","lng"] },
    headerRatingPill: { cols: ["rating_overall","rating"] },
  };
  // ─────────────────────────────────────────────────────────────────────────────

  async function load() {
    if (!slug) { el.title.textContent = "Not found"; return; }
    // CACHE-BUSTED FETCH (step ⑤)
    const res = await fetch("data/tools.json?ts=" + Date.now(), { cache: "no-store" });
    if (!res.ok) { el.title.textContent = "Not found"; return; }
    const data = await res.json();
    const tool = (data || []).find(t => (t.slug||"").toLowerCase() === slug);
    if (!tool) { el.title.textContent = "Not found"; return; }
    render(tool, data);
  }

  function render(item, all) {
    // Identity
    el.title.textContent = item.name || "Untitled";
    const primaryCat = (Array.isArray(item.categories) && item.categories[0]) || "";
    const catSlug = slugify(primaryCat);

    // ── Data-driven visibility: compute once per item
    const features = {};
    const extra = {
      rating: [(it) => typeof it.rating_overall === 'number'
                     || typeof it.rating === 'number'
                     || (it.subscores && Object.keys(it.subscores).length)],
      hours:  [(it) => !!(it.hours && it.hours.weekly)],
      map:    [(it) => !!(it.location && (it.location.lat || it.location.lng || it.address))],
      details:[(it) => true], // we still hide later if nothing ultimately renders
    };
    Object.entries(FEATURE_REQUIREMENTS).forEach(([key, req]) => {
      const cols = req.cols || [];
      const schemaOK = hasSchema(item, cols);
      const dataOK   = hasData(item, cols, extra[key] || []);
      features[key]  = schemaOK && dataOK;
    });

    // Optional: category class hook for CSS
    document.body.classList.add(`cat-${catSlug || 'unknown'}`);

    // Apply visibility to cards immediately
    (features.about     ? showCard : hideCard)('about');
    (features.amenities ? showCard : hideCard)('amenities');
    (features.cuisines  ? showCard : hideCard)('cuisines');
    (features.meals     ? showCard : hideCard)('meals');
    (features.rating    ? showCard : hideCard)('rating');
    (features.hours     ? showCard : hideCard)('hours');
    (features.map       ? showCard : hideCard)('map');
    (features.details   ? showCard : hideCard)('facts');
    // --- Subnav: remove links to sections that are hidden/missing ---
(function pruneSubnav() {
  const nav    = document.querySelector('.detail-subnav');
  const spacer = document.getElementById('detail-subnav-spacer');
  if (!nav) return;

  // List the section IDs that might appear in the subnav
  const ids = ['about','amenities','cuisines','meals','rating','hours','map','facts'];

  // Remove any <a> whose target section is hidden or missing
  let kept = 0;
  ids.forEach(id => {
    const a   = nav.querySelector(`a[href="#${id}"]`);
    const sec = document.getElementById(id);
    if (!a) return;
    const hide = !sec || sec.hasAttribute('hidden');
    if (hide) a.remove();
    else kept++;
  });

  // If nothing left, hide the subnav and spacer
  if (kept === 0) {
    nav.style.display = 'none';
    if (spacer) spacer.style.display = 'none';
  }
})();


    // Minimal SEO updates
    document.title = `${item.name} — ${primaryCat || "Place"} | Best Muscat`;
    const og = (p,v)=>{ const sel = p.startsWith('og:') ? 'property' : 'name'; const m=document.querySelector(`meta[${sel}="${p}"]`); if(m) m.setAttribute("content", v); };
    og("og:title", document.title);
    og("og:description", item.tagline || item.description || "Discover places in Muscat");
    og("twitter:title", document.title);
    og("twitter:description", item.tagline || item.description || "Discover places in Muscat");

    // Hero image: prefer images.hero → image → hero_url → logo_url
    const hero = item.image || (item.images && (item.images.hero || item.images.logo)) || item.hero_url || item.logo_url || "";
    if (hero) { el.hero.src = hero; el.hero.alt = item.name; } else { el.hero.style.display = "none"; }

    // Actions
    const website = item.actions?.website || item.url || "";
    const phone   = item.actions?.phone   || "";
    const maps    = item.actions?.maps_url || (item.location?.lat && item.location?.lng
                    ? `https://www.google.com/maps?q=${item.location.lat},${item.location.lng}` : "");
    if (website) { el.btnVisit.href = website; el.btnVisit.hidden = false; }
    if (phone)   { el.btnCall.href  = `tel:${phone}`; el.btnCall.hidden = false; }
    if (maps)    { el.btnMaps.href  = maps; el.btnMaps.hidden = false; }

    el.btnShare.addEventListener("click", async ()=>{
      try { await navigator.clipboard.writeText(location.href); el.btnShare.textContent = "Copied!"; setTimeout(()=> el.btnShare.textContent="Share Link", 1200); }
      catch { alert("Copy failed"); }
    });

    // Pills
    const price = item.price || item.pricing || "";
    if (price)       { el.price.textContent = String(price).toUpperCase(); el.price.hidden = false; }
    if (primaryCat)  { el.cat.textContent   = primaryCat;                  el.cat.hidden = false; }

    // Header rating pill (legacy overall, if present)
    if (typeof item.rating === "number" || (typeof item.rating === "string" && item.rating.trim())) {
      el.rating.textContent = `${item.rating}/10`;
      el.rating.hidden = false;
    }
    // Hide header pill if feature says so
    if (!features.headerRatingPill) { document.getElementById('d-rating')?.setAttribute('hidden',''); }

    // Open/Closed (if hours.weekly exists)
    const state = openState(item.hours);
    if (state) { el.open.textContent = state; el.open.hidden = false; }

    // About
    if (features.about) {
      el.about.textContent = item.description || item.tagline || "—";
    }

    // Hours
    if (features.hours) {
      el.hours.innerHTML = renderHours(item.hours);
    }

    // Location
    if (features.map) {
      el.loc.innerHTML = renderLocation(item);
    }

    // Aside details
    if (features.details) {
      fillDetails(item);
    }

    // --- Chips for amenities / cuisines / meals ---
    // Hides the entire section when the array is missing/empty.  (step ④)
    (function renderChips() {
      function mountChips(sectionId, chipRootId, values) {
        const section = document.getElementById(sectionId);
        const root    = document.getElementById(chipRootId);
        if (!section || !root) return;

        if (!Array.isArray(values) || values.length === 0) {
          section.setAttribute('hidden','');  // hide whole card
          root.innerHTML = '';
          return;
        }
        root.innerHTML = values.map(v => `<span class="chip">${String(v)}</span>`).join('');
        section.removeAttribute('hidden');
      }

      mountChips('amenities', 'd-amenities', item.amenities);
      mountChips('cuisines',  'd-cuisines',  item.cuisines);
      mountChips('meals',     'd-meals',     item.meals);
    })();

    // ---- DEFENSIVE: enforce hide if no data (catches any later un-hide) ----
    (function enforceChipVisibility() {
      if (!Array.isArray(item.amenities) || item.amenities.length === 0) hideCard('amenities');
      if (!Array.isArray(item.cuisines)  || item.cuisines.length  === 0) hideCard('cuisines');
      if (!Array.isArray(item.meals)     || item.meals.length     === 0) hideCard('meals');
    })();

    // --- Rating pill & subscores (card in main column) ---
    if (features.rating) (function renderRating() {
      const pill = document.getElementById('rating-pill');
      const grid = document.getElementById('d-scores');
      if (!pill || !grid) return;

      // Overall: prefer item.rating_overall, fallback to numeric item.rating
      const overall = (typeof item.rating_overall === 'number')
        ? item.rating_overall
        : (typeof item.rating === 'number' ? item.rating : null);

      if (typeof overall === 'number') {
        pill.textContent = `${overall.toFixed(1)} / 10`;
        pill.classList.add('pill--rating');
        pill.hidden = false;
      }

      // Subscores object: prefer item.subscores; fallback to item.scores
      const subs = (item.subscores && typeof item.subscores === 'object')
        ? item.subscores
        : ((item.scores && typeof item.scores === 'object') ? item.scores : null);

      if (subs) {
        const rows = Object.entries(subs)
          .filter(([, v]) => typeof v === 'number')
          .map(([k, v]) => `<div class="score-row"><span>${esc((k||'').replace(/_/g,' '))}</span><strong>${v.toFixed(2)}</strong></div>`)
          .join('');
        if (rows) {
          grid.innerHTML = rows;
          grid.hidden = false;
        }
      }

      // Public sentiment (optional)
      const ps = item.public_sentiment;
      const psBox = document.getElementById('d-public-sentiment');
      if (ps && psBox) {
        const bits = [];
        if (ps.source)       bits.push(`<strong>${esc(ps.source)}</strong>`);
        if (ps.count)        bits.push(`${esc(String(ps.count))} reviews`);
        if (ps.summary)      bits.push(esc(ps.summary));
        if (ps.last_updated) bits.push(`<span class="muted">Updated ${esc(ps.last_updated)}</span>`);
        psBox.innerHTML = bits.join(' · ');
        psBox.hidden = bits.length === 0;
      }
    })();

    // Related: same primary category, exclude current
    const rel = (all||[]).filter(t =>
      t.slug !== item.slug &&
      Array.isArray(t.categories) &&
      t.categories.length &&
      slugify(t.categories[0]) === catSlug
    ).slice(0,10);
    el.relatedGrid.innerHTML = rel.map(cardHTML).join("");

    // Hide related section if empty
    const relatedSection = document.getElementById("related");
    if (relatedSection) relatedSection.style.display = el.relatedGrid.childElementCount ? "" : "none";
  }

  // === helpers ===
  function cardHTML(t){
    const img = t.image || (t.images && (t.images.hero || t.images.logo)) || t.hero_url || t.logo_url || "";
    return `
      <article class="card card--place">
        <a class="card-img" href="tool.html?slug=${encodeURIComponent(t.slug)}" aria-label="${esc(t.name)} details">
          ${img ? `<img src="${esc(img)}" alt="${esc(t.name)}" loading="lazy" decoding="async"/>`
                : `<div class="img-placeholder">${esc((t.name||'').split(/\s+/).slice(0,2).map(s=>s[0]?.toUpperCase()||'').join('')||'BM')}</div>`}
        </a>
        <div class="card-body">
          <h3 class="card-title"><a class="card-link" href="tool.html?slug=${encodeURIComponent(t.slug)}">${esc(t.name)}</a></h3>
          <p class="card-sub">${esc(t.tagline || "")}</p>
          <div class="badges">${(t.categories||[]).slice(0,2).map(c=>`<span class="badge">${esc(c)}</span>`).join(" ")}</div>
        </div>
      </article>
    `;
  }

  function openState(hours){
    try{
      if (!hours || !hours.weekly) return "";
      const now = new Date();
      const dow = ["sun","mon","tue","wed","thu","fri","sat"][now.getDay()];
      const todays = hours.weekly[dow];
      if (!Array.isArray(todays) || !todays.length) return "";
      const hh = n=>String(n).padStart(2,"0");
      const cur = parseInt(hh(now.getHours())+hh(now.getMinutes()),10);
      const isOpen = todays.some(w=>{
        const a = String(w.start || "").replace(":","").slice(0,4);
        const b = String(w.end   || "").replace(":","").slice(0,4);
        const s = parseInt(a,10), e = parseInt(b,10);
        return Number.isFinite(s) && Number.isFinite(e) && cur >= s && cur < e;
      });
      return isOpen ? "Open" : "Closed";
    }catch{ return ""; }
  }

  function renderHours(hours){
    if (!hours || !hours.weekly) return "<div class='muted'>—</div>";
    const dayNames = [["mon","Mon"],["tue","Tue"],["wed","Wed"],["thu","Thu"],["fri","Fri"],["sat","Sat"],["sun","Sun"]];
    const tr = dayNames.map(([key,lab])=>{
      const arr = hours.weekly[key] || [];
      if (!arr.length) return `<tr><td>${lab}</td><td colspan="2">—</td></tr>`;
      return arr.map((w,i)=>`
        <tr${i>0?" class='cont'":""}>
          ${i===0?`<td rowspan="${arr.length}">${lab}</td>`:""}
          <td>${esc((w.start||"").slice(0,5))}</td>
          <td>${esc((w.end||"").slice(0,5))}</td>
        </tr>
      `).join("");
    }).join("");
    return `
      <table class="hours">
        <thead><tr><th>Day</th><th>Opening</th><th>Closing</th></tr></thead>
        <tbody>${tr}</tbody>
      </table>
    `;
  }

  function renderLocation(item){
    const loc = item.location || {};
    const n = item.neighborhood || loc.neighborhood || "";
    const a = item.address || loc.address || "";
    const c = item.city || loc.city || "Muscat";
    const country = item.country || loc.country || "Oman";

    // Build a query for Maps: prefer address → lat,lng → name
    const hasAddr = (a || "").trim().length > 0;
    const hasLatLng = (typeof loc.lat === "number" && typeof loc.lng === "number");
    const q = hasAddr
      ? encodeURIComponent(a)
      : (hasLatLng
          ? encodeURIComponent(`${loc.lat},${loc.lng}`)
          : encodeURIComponent(item.name || "Muscat"));

    // If your data already provided a custom embed (loc.map_embed), use it
    const mapEmbedHTML = loc.map_embed
      ? `<div class="map-embed">${loc.map_embed}</div>`
      : (q
          ? `<div class="map-embed">
               <iframe
                 style="width:100%;height:320px;border:0;border-radius:12px;"
                 loading="lazy"
                 referrerpolicy="no-referrer-when-downgrade"
                 src="https://www.google.com/maps?q=${q}&output=embed">
               </iframe>
             </div>`
          : "");

    // Helpful action links
    const website = item.actions?.website || item.url || loc.website || "";
    const phone   = item.actions?.phone   || loc.phone || "";
    const goHref  = item.actions?.maps_url
                    || (q ? `https://www.google.com/maps/search/?api=1&query=${q}` : "");

    const websiteRow    = website ? `<p><a href="${esc(website)}" target="_blank" rel="noopener">Website ↗</a></p>` : "";
    const phoneRow      = phone   ? `<p><a href="tel:${esc(phone)}">Call</a></p>` : "";
    const directionsRow = goHref  ? `<p><a href="${esc(goHref)}" target="_blank" rel="noopener">Get Directions ↗</a></p>` : "";

    const lines = [];
    if (n) lines.push(`<div><strong>Neighbourhood:</strong> ${esc(n)}</div>`);
    if (a || c || country) lines.push(`<div><strong>Address:</strong> ${esc([a,c,country].filter(Boolean).join(", "))}</div>`);

    return `
      ${mapEmbedHTML}
      ${lines.join("") || "<div class='muted'>—</div>"}
      ${websiteRow}${phoneRow}${directionsRow}
    `;
  }

  function fillDetails(item){
    const push = (k,v)=>{
      if (!v) return;
      el.aside.insertAdjacentHTML("beforeend", `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`);
    };
    if (Array.isArray(item.categories) && item.categories.length) push("Category", item.categories[0]);
    if (Array.isArray(item.tags) && item.tags.length)             push("Tags", item.tags.join(", "));
    if (item.price || item.pricing)                               push("Price Range", String(item.price||item.pricing));
    if (item.neighborhood)                                        push("Neighbourhood", item.neighborhood);
    if (item.city || item.country)                                push("City / Country", [item.city, item.country].filter(Boolean).join(", "));
    if (item.location?.lat && item.location?.lng)                 push("Coordinates", `${item.location.lat}, ${item.location.lng}`);
  }

  // start: load data and render
  load().catch(()=>{ document.getElementById("d-title").textContent="Error loading"; });

  // --- Floating subnav + Scroll spy for .detail-subnav ---
  (function setupFloatingSubnav() {
    const header = document.querySelector('.site-header');
    const nav = document.querySelector('.detail-subnav');
    const spacer = document.getElementById('detail-subnav-spacer');
    if (!nav || !spacer) return;

    // 1) Make it fixed and position it right below the header
    function positionNav() {
      const headH = header ? header.offsetHeight : 0;
      nav.classList.add('fixed');
      nav.style.top = headH + 'px';

      // After it's fixed, measure its height and set spacer
      const navH = nav.offsetHeight;
      spacer.style.height = navH + 'px';
    }

    // 2) Scroll-spy (active link highlight)
    const links = [...nav.querySelectorAll('a[href^="#"]')];
    const ids = links.map(a => a.getAttribute('href').slice(1));
    const sections = ids.map(id => document.getElementById(id)).filter(Boolean);

    const activate = (id) => {
      links.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + id));
    };

    const obs = new IntersectionObserver((entries) => {
      const visible = entries
        .filter(e => e.isIntersecting)
        .sort((a,b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (visible?.target?.id) activate(visible.target.id);
    }, { rootMargin: '-40% 0px -50% 0px', threshold: [0, 0.33, 0.66, 1] });

    sections.forEach(s => obs.observe(s));

    // Smooth scroll
    nav.addEventListener('click', (e) => {
      const a = e.target.closest('a[href^="#"]');
      if (!a) return;
      e.preventDefault();
      const id = a.getAttribute('href').slice(1);
      const el2 = document.getElementById(id);
      if (!el2) return;
      el2.scrollIntoView({ behavior: 'smooth', block: 'start' });
      activate(id);
    });

    // 3) Initialize and update on resize (header height can change on responsive)
    function onReady() { positionNav(); }
    window.addEventListener('resize', positionNav);
    // If fonts load and change sizes, remeasure shortly after load
    window.addEventListener('load', () => setTimeout(positionNav, 50));

    // Run immediately
    onReady();
  })();
})();
