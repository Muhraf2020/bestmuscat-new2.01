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

  function esc(s){ return String(s||""); }
  function slugify(s){ return (s||"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,""); }

  async function load() {
    if (!slug) { el.title.textContent = "Not found"; return; }
    const res = await fetch("data/tools.json", { cache: "no-store" });
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

    // Actions (aligned to your pipeline fields)
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
    if (primaryCat)  { el.cat.textContent   = primaryCat;                 el.cat.hidden = false; }

    // Rating (optional)
    if (typeof item.rating === "number" || (typeof item.rating === "string" && item.rating.trim())) {
      el.rating.textContent = `${item.rating}/10`;
      el.rating.hidden = false;
    }

    // Open/Closed (if hours.weekly exists)
    const state = openState(item.hours);
    if (state) { el.open.textContent = state; el.open.hidden = false; }

    // About
    el.about.textContent = item.description || item.tagline || "—";

    // Hours
    el.hours.innerHTML = renderHours(item.hours);

    // Location
    el.loc.innerHTML = renderLocation(item);

    // Aside details
    fillDetails(item);

    // Scores (optional object)
    if (item.scores && typeof item.scores === "object") {
      el.scores.hidden = false;
      el.scores.innerHTML = Object.entries(item.scores).map(([k,v]) => {
        const label = k.replace(/_/g," ").replace(/\b\w/g,m=>m.toUpperCase());
        const val = (v && typeof v === "number") ? v.toFixed(2) : v;
        return `<div class="score"><span class="score-name">${esc(label)}</span><span class="score-val">${esc(val)}</span></div>`;
      }).join("");
    }

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
    const n = item.neighborhood || item.location?.neighborhood || "";
    const a = item.address || item.location?.address || "";
    const c = item.city || item.location?.city || "Muscat";
    const country = item.country || item.location?.country || "Oman";
    const bits = [];
    if (n) bits.push(`<div><strong>Neighbourhood:</strong> ${esc(n)}</div>`);
    if (a || c || country) bits.push(`<div><strong>Address:</strong> ${esc([a,c,country].filter(Boolean).join(", "))}</div>`);
    return bits.join("") || "<div class='muted'>—</div>";
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

  // start
  load().catch(()=>{ document.getElementById("d-title").textContent="Error loading"; });
})();
