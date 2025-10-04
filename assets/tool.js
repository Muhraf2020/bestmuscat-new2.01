(function(){
  const qs = new URLSearchParams(location.search);
  const slug = (qs.get("slug") || "").trim().toLowerCase();

  const el = {
    title:   document.getElementById("d-title"),
    excerpt: document.getElementById("d-excerpt"),
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
  function isValidUrl(u){
  try{ const x=new URL(u); return ['http:','https:'].includes(x.protocol); }catch{ return false; }
  }
  function isExampleDomain(u){
    return /(^|\.)example\.com$/i.test((()=>{try{return new URL(u).hostname;}catch{return''}})());
  }

  // ── Category gating: which sections are allowed for which categories ──
  // Keys are lowercased slugs for your primary categories (slugify of the label in CSV).
  // If a category is not listed here, sections default to "allowed" (still need data present).
  const CATEGORY_ALLOW = {
    // Food venues
    "restaurants": {
      cuisines: true, meals: true, eventFacts: false
    },
    // Cafes (if you ever have them)
    "cafes": {
      cuisines: true, meals: true, eventFacts: false
    },
    // Catering: sometimes cuisines yes, meals usually no
    "catering-services": {
      cuisines: true, meals: false, eventFacts: false
    },
    // Events: show event facts, never cuisines/meals
    "events": {
      cuisines: false, meals: false, eventFacts: true
    },
    // Everything else uses defaults (no special extras)
    "hotels": {},
    "spas": {},
    "clinics": {},
    "schools": {},
    "malls": {},
    "car-repair-garages": {},
    "home-maintenance-and-repair": {},
    "moving-and-storage": {}
  };
  
  // Helper: is a feature allowed for this category?
  function allowedForCategory(sectionKey, catSlug) {
    const cfg = CATEGORY_ALLOW[catSlug] || CATEGORY_ALLOW[catSlugify(catSlug)] || {};
    // default allow = true unless explicitly set to false
    if (sectionKey in cfg) return !!cfg[sectionKey];
    return true;
  }
  function catSlugify(s){ return slugify(s || ""); }

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
  
      // Special-case the nested "about" object: treat as data if it has short/long
      if (c === "about") {
        const nested = item.about && (item.about.short || item.about.long);
        return !!(nested && String(nested).trim());
      }
  
      // If the value is an object, treat it as non-empty if any nested string is non-empty
      if (v && typeof v === "object") {
        return Object.values(v).some(x => x !== undefined && x !== null && String(x).trim() !== "");
      }
  
      // Default checks
      return Array.isArray(v) ? v.length > 0 : (v !== undefined && v !== null && String(v).trim() !== "");
    });
  
    const extraHit = extraChecks.some(fn => { try { return !!fn(item); } catch(e){ return false; }});
    return valHit || extraHit;
  }


  // One-time mapping from UI sections → relevant CSV columns
  const FEATURE_REQUIREMENTS = {
    about:     { cols: ["about","about_short","about_long","description","tagline"] },
    amenities: { cols: ["amenities"] },
    cuisines:  { cols: ["cuisines"] },
    meals:     { cols: ["meals"] },
    rating:    { cols: ["rating_overall","sub_food_quality","sub_service","sub_ambience","sub_value","sub_accessibility","subscores","scores","public_sentiment"] },
    hours:     { cols: ["hours_raw"] }, // parsed into item.hours
    map:       { cols: ["address","lat","lng","maps_url"] },
    details:   { cols: ["categories","tags","pricing","price_range","neighborhood","city","country","lat","lng"] },
    headerRatingPill: { cols: ["rating_overall","rating"] },
    // make sure this exists:
    eventFacts: { cols: ["fact_venue","fact_date","fact_time","fact_ticket_price"] }
  };
  // ── Per-category preferred fields (by CSV column name) in the "Details" card.
  // Use the column names exactly as they appear in your CSVs.
  const CATEGORY_FACTS = {
    "hotels": {
      fields: [
        ["Neighbourhood", "neighborhood"],
        ["City / Country", null],
        ["Price Range", "price_range"],
        ["Tags", "tags"],
        ["Website", null],
        ["Phone", null],
      ],
      hideSections: [] // show all applicable sections
    },
    "restaurants": {
      fields: [
        ["Neighbourhood", "neighborhood"],
        ["City / Country", null],
        ["Price Range", "price_range"],
        ["Tags", "tags"],
        ["Website", null],
        ["Phone", null],
      ],
      hideSections: [] // cuisines/meals are already handled as separate cards
    },
    "spas": {
      fields: [
        ["Neighbourhood", "neighborhood"],
        ["City / Country", null],
        ["Price Range", "price_range"],
        ["Tags", "tags"],
        ["Website", null],
        ["Phone", null],
      ],
      hideSections: ["cuisines","meals"]
    },
    "clinics": {
      fields: [
        ["Neighbourhood", "neighborhood"],
        ["City / Country", null],
        ["Tags", "tags"],
        ["Website", null],
        ["Phone", null],
      ],
      hideSections: ["cuisines","meals"]
    },
    "malls": {
      fields: [
        ["Neighbourhood", "neighborhood"],
        ["City / Country", null],
        ["Tags", "tags"],
        ["Website", null],
        ["Phone", null],
      ],
      hideSections: ["cuisines","meals"]
    },
    "car-repair-garages": {
      fields: [
        ["Neighbourhood", "neighborhood"],
        ["City / Country", null],
        ["Tags", "tags"],
        ["Website", null],
        ["Phone", null],
      ],
      hideSections: ["cuisines","meals"]
    },
    "home-maintenance-and-repair": {
      fields: [
        ["Neighbourhood", "neighborhood"],
        ["City / Country", null],
        ["Tags", "tags"],
        ["Website", null],
        ["Phone", null],
      ],
      hideSections: ["cuisines","meals"]
    },
    "catering-services": {
      fields: [
        ["Neighbourhood", "neighborhood"],
        ["City / Country", null],
        ["Price Range", "price_range"],
        ["Tags", "tags"],
        ["Website", null],
        ["Phone", null],
      ],
      hideSections: ["cuisines","meals"]
    },
  
    // Events / Events Planning (support both labels)
    "events": {
      fields: [
        ["Venue", "fact_venue"],
        ["Date", "fact_date"],
        ["Time", "fact_time"],
        ["Ticket Price", "fact_ticket_price"],
        ["Neighbourhood", "neighborhood"],
        ["City / Country", null],
        ["Tags", "tags"],
        ["Website", null],
        ["Phone", null],
      ],
      hideSections: ["cuisines","meals"] // events shouldn't show cuisines/meals
    },
    "events-planning": { // if you use this label anywhere
      fields: [
        ["Venue", "fact_venue"],
        ["Date", "fact_date"],
        ["Time", "fact_time"],
        ["Ticket Price", "fact_ticket_price"],
        ["Neighbourhood", "neighborhood"],
        ["City / Country", null],
        ["Tags", "tags"],
        ["Website", null],
        ["Phone", null],
      ],
      hideSections: ["cuisines","meals"]
    },
  };
  
  // Keys we never echo in Details (already used elsewhere or internal)
  const EXCLUDE_DETAIL_KEYS = new Set([
    "id","slug","name","category","categories","tagline",
    "description","about","about_short","about_long",
    "logo_url","hero_url","image_credit","image_source_url",
    "place_id","osm_type","osm_id","wikidata_id",
    "pricing","price","price_range",
    "rating","rating_overall","subscores","scores",
    "public_sentiment","public_reviews",
    "review_count","review_source","review_insight","last_updated",
    "hours_raw","hours",
    "neighborhood","address","city","country","lat","lng",
    "website","phone","maps_url","url",
    "actions","images","image","hero","gallery",
    "schema_keys","present_keys","location","created_at",
    "amenities","cuisines","meals" // rendered as dedicated cards
  ]);
  
  // Treat these prefixes as non-detail/system
  const EXCLUDE_PREFIXES = ["sub_", "review_", "image_", "actions.", "location.", "images."];
  
  // Pretty label from a CSV key (fact_venue -> Venue; foo_bar -> Foo Bar)
  function labelFromKey(k){
    if (!k) return "";
    let name = String(k);
    if (name.startsWith("fact_")) name = name.slice(5);
    name = name.replace(/[_\-]+/g, " ").trim();
    return name.replace(/\b\w/g, c => c.toUpperCase());
  }
  
  // Should this key be auto-rendered as an extra?
  function shouldAutoShowKey(k){
    if (!k) return false;
    if (EXCLUDE_DETAIL_KEYS.has(k)) return false;
    if (EXCLUDE_PREFIXES.some(p => k.startsWith(p))) return false;
    // prefer keys that start with fact_ or are simple scalars (string/number/bool)
    return true;
  }
  
  // Grab the category config by slug of the primary category
  function getCategoryConfig(primaryCatLabel){
    const slug = (primaryCatLabel||"").toLowerCase()
      .replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,"");
    return CATEGORY_FACTS[slug] || null;
  }

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
    // Short blurb under the title: nested about.short → flat → description → tagline
    const short =
      (item.about && (item.about.short || item.about.long)) ||
      item.about_short || item.about_long ||
      item.description || item.tagline || "";
    if (short && String(short).trim()) {
      el.excerpt.textContent = short;
      el.excerpt.hidden = false;
    } else {
      el.excerpt.hidden = true;
    }

    const primaryCat = (Array.isArray(item.categories) && item.categories[0]) || "";
    const catSlug = slugify(primaryCat);
    // Display-only rename: keep data as "Events" but show "Events Planning"
    const displayCat = (primaryCat || "").toLowerCase() === "events"
      ? "Events Planning"
      : primaryCat;


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
      const catOK    = allowedForCategory(key, catSlug);   // NEW: category gating
      features[key]  = schemaOK && dataOK && catOK;
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
    
    
    // Enforce per-category hides (e.g., hide cuisines/meals for Events)
    (function enforceCategoryHides(){
      const cfg = getCategoryConfig(primaryCat);
      if (!cfg || !Array.isArray(cfg.hideSections)) return;
      cfg.hideSections.forEach(id => hideCard(id));
    })();


    // Hide dead sub-nav links for sections that are hidden/absent
    (function hideEmptyNavLinks() {
      const nav = document.querySelector('.detail-subnav');
      if (!nav) return;
      // Your tool.html subnav currently has these anchors:
      const ids = ['about','amenities','cuisines','meals','rating','hours','map'];
      ids.forEach(id => {
        const section = document.getElementById(id);
        const link = nav.querySelector(`a[href="#${id}"]`);
        if (link && (!section || section.hasAttribute('hidden'))) {
          link.style.display = 'none';
        }
      });
    })();


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

    // Prefer canonical fields from CSV; fall back to legacy/actions if present
    const websiteRaw = item.website || item.actions?.website || item.url || "";
    const phone      = item.phone   || item.actions?.phone   || "";
    const maps       = (item.maps_url && item.maps_url.startsWith('https://www.google.com/maps/'))
      ? item.maps_url
      : (item.location?.lat && item.location?.lng
          ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(item.name||'')}&query_place_id=${encodeURIComponent(item.place_id||'')}`
          : "");
    
    // 1) Maps — always show if we can build a Google Maps link
    if (maps) {
      el.btnMaps.href  = maps;
      el.btnMaps.hidden = false;
    }
    
    // 2) Website / Suggest Website
    const hasRealWebsite = isValidUrl(websiteRaw) && !isExampleDomain(websiteRaw);
    if (hasRealWebsite) {
      el.btnVisit.textContent = "Visit";
      el.btnVisit.href = websiteRaw;
      el.btnVisit.hidden = false;
    } else {
      // Point to our suggestion page with the current slug
      const suggestUrl = `suggest.html?slug=${encodeURIComponent(item.slug || '')}`;
      el.btnVisit.textContent = "Suggest Website";
      el.btnVisit.href = suggestUrl;
      el.btnVisit.hidden = false;
    }
    
    // 3) Phone (optional)
    if (phone) {
      el.btnCall.href  = `tel:${phone}`;
      el.btnCall.hidden = false;
    }


    el.btnShare.addEventListener("click", async ()=>{
      try { await navigator.clipboard.writeText(location.href); el.btnShare.textContent = "Copied!"; setTimeout(()=> el.btnShare.textContent="Share Link", 1200); }
      catch { alert("Copy failed"); }
    });

    // Pills
    const price = item.price || item.pricing || "";
    if (price)       { el.price.textContent = String(price).toUpperCase(); el.price.hidden = false; }
    if (displayCat)  { el.cat.textContent   = displayCat;                  el.cat.hidden = false; }


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

    // About (prefer nested about.long/short → flat → description → tagline)
    if (features.about) {
      const longTxt =
        (item.about && (item.about.long || item.about.short)) ||
        item.about_long || item.about_short ||
        item.description || item.tagline || "—";
      el.about.textContent = longTxt;
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
    // utility to add a row
    const push = (label, value) => {
      if (value === undefined || value === null) return;
      const str = Array.isArray(value) ? value.join(", ") : String(value).trim();
      if (!str) return;
      el.aside.insertAdjacentHTML("beforeend", `<dt>${esc(label)}</dt><dd>${esc(str)}</dd>`);
    };
  
    // Basics always first
    const primaryCat = (Array.isArray(item.categories) && item.categories[0]) || "";
    if (primaryCat) push("Category", primaryCat);
  
    const cfg = getCategoryConfig(primaryCat);
  
    // Preferred rows for this category (in your chosen order)
    if (cfg && Array.isArray(cfg.fields)) {
      cfg.fields.forEach(([label, key]) => {
        if (label === "City / Country" && key === null) {
          const cc = [item.city, item.country].filter(Boolean).join(", ");
          if (cc) push(label, cc);
          return;
        }
        if (label === "Website" && key === null) {
          const url = item.actions?.website || item.url;
          if (url) push(label, url);
          return;
        }
        if (label === "Phone" && key === null) {
          const phone = item.actions?.phone;
          if (phone) push(label, phone);
          return;
        }
        if (key) {
          const v = item[key];
          if (v !== undefined && v !== null && String(v).trim() !== "") push(label, v);
        }
      });
    } else {
      // Generic fallback when no per-category config: show common basics
      if (item.neighborhood) push("Neighbourhood", item.neighborhood);
      const cc = [item.city, item.country].filter(Boolean).join(", ");
      if (cc) push("City / Country", cc);
      if (item.price_range || item.pricing) push("Price Range", item.price_range || item.pricing);
      if (Array.isArray(item.tags) && item.tags.length) push("Tags", item.tags.join(", "));
      const url = item.actions?.website || item.url;
      if (url) push("Website", url);
      if (item.actions?.phone) push("Phone", item.actions.phone);
    }
  
    // Coordinates (nice to have, if present)
    if (item.location?.lat && item.location?.lng) {
      push("Coordinates", `${item.location.lat}, ${item.location.lng}`);
    }
  
    // Auto-include any extra CSV columns not already shown, e.g., fact_* fields
    const shownLabels = new Set([...el.aside.querySelectorAll("dt")].map(dt => dt.textContent.trim().toLowerCase()));
    const schema = Array.isArray(item.schema_keys) ? item.schema_keys : [];
    schema.forEach((k) => {
      if (!shouldAutoShowKey(k)) return;
      const v = item[k];
      if (v === undefined || v === null) return;
      const str = Array.isArray(v) ? v.join(", ") : String(v).trim();
      if (!str) return;
  
      const label = labelFromKey(k);
      // Avoid duplicates (case-insensitive)
      if (shownLabels.has(label.toLowerCase())) return;
  
      push(label, str);
    });
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
