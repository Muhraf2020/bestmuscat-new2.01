/* app.enhanced.js — additive features; safe to include alongside your existing app.js */
(function(){
  function parseQuery() {
    const q = {};
    (location.search || '').replace(/^\?/, '').split('&').forEach(kv => {
      if (!kv) return;
      const [k,v] = kv.split('=');
      q[decodeURIComponent(k)] = decodeURIComponent((v||'').replace(/\+/g,' '));
    });
    return q;
  }
  function loadJSON(path){ return fetch(path).then(r=>r.json()); }

  function isOpenNow(hours, now=new Date()){
    try{
      const days = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
      const day = days[now.getDay()];
      const slots = (hours && hours[day]) || [];
      const mins = now.getHours()*60 + now.getMinutes();
      for(const [open, close] of slots){
        const [oh,om] = open.split(':').map(Number);
        const [ch,cm] = close.split(':').map(Number);
        let o = oh*60+om, c = ch*60+cm;
        if (c <= o) c += 24*60; // overnight
        let m = mins;
        if (m < o) m += 24*60;
        if (m >= o && m <= c) return true;
      }
      return false;
    }catch(e){ return false; }
  }

  function injectJSONLD(place){
    const ld = {
      "@context":"https://schema.org",
      "@type":"LocalBusiness",
      "name": place.name,
      "url": location.href,
      "address": place.location && place.location.address,
      "telephone": place.actions && place.actions.phone || undefined,
      "image": (place.gallery||[])[0],
      "aggregateRating": place.rating_overall ? {
        "@type":"AggregateRating",
        "ratingValue": place.rating_overall,
        "reviewCount": (place.public_sentiment && place.public_sentiment.count) || 0
      }: undefined,
      "openingHoursSpecification": Object.entries(place.hours||{}).map(([d,slots])=> (slots||[]).map(s=>{
        return {"@type":"OpeningHoursSpecification","dayOfWeek":d,"opens":s[0],"closes":s[1]};
      })).flat(),
      "servesCuisine": place.cuisines,
      "priceRange": place.price_range && place.price_range.symbol
    };
    const s = document.createElement('script');
    s.type = 'application/ld+json';
    s.textContent = JSON.stringify(ld);
    document.head.appendChild(s);
    if ((place.faqs||[]).length){
      const faq = {"@context":"https://schema.org","@type":"FAQPage","mainEntity": place.faqs.map(x=>({ "@type":"Question", "name":x.q, "acceptedAnswer":{"@type":"Answer","text":x.a}}))};
      const s2 = document.createElement('script'); s2.type='application/ld+json'; s2.textContent = JSON.stringify(faq);
      document.head.appendChild(s2);
    }
  }

  function renderDetailExtras(place){
    const root = document.querySelector('#place-details') || document.querySelector('[data-place-details]') || document.querySelector('main') || document.body;
    const wrap = document.createElement('section');
    wrap.className = 'bm-extras';
    const openLabel = isOpenNow(place.hours) ? 'Open' : 'Closed';
    const status = `<span class="status badge">${openLabel}</span>`;
    const badges = (place.badges||[]).map(b=>`<span class="badge">${b}</span>`).join(' ');
    const dishes = (place.dishes||[]).map(d=>`<li>${d}</li>`).join('');
    const amns = (place.amenities||[]).map(a=>`<li>${a}</li>`).join('');
    const times = (place.best_times||[]).map(t=>`<li><strong>${t.label}:</strong> ${t.window}</li>`).join('');
    const sentiment = place.public_sentiment ? `<p><em>${place.public_sentiment.summary||''}</em> (${place.public_sentiment.count||0} reviews; updated ${place.public_sentiment.last_updated||''})</p>` : '';

    wrap.innerHTML = `
      <div class="extras-grid">
        <div>
          <h3>Badges</h3>
          <p>${status} ${badges || '—'}</p>
          <h3>Verified & Methodology</h3>
          <p>${place.verified ? 'Verified' : 'Unverified'}${place.methodology_note ? ' — ' + place.methodology_note : ''}</p>
          <h3>Best Times</h3>
          <ul>${times || '<li>—</li>'}</ul>
          <h3>Public Sentiment</h3>
          ${sentiment || '—'}
        </div>
        <div>
          <h3>Dishes</h3>
          <ul>${dishes || '<li>—</li>'}</ul>
          <h3>Amenities</h3>
          <ul>${amns || '<li>—</li>'}</ul>
          <h3>FAQs</h3>
          <ul>${(place.faqs||[]).map(f=>`<li><strong>${f.q}</strong><br>${f.a}</li>`).join('') || '<li>—</li>'}</ul>
        </div>
      </div>
    `;
    root.appendChild(wrap);
  }

  function enhanceDetail(){
    const q = parseQuery();
    if (!q.slug) return;
    loadJSON('data/places.json').then(rows => {
      const place = rows.find(p => p.slug === q.slug);
      if (!place) return;
      injectJSONLD(place);
      renderDetailExtras(place);
    });
  }

  // Compact list toggle (if container present)
  function enhanceList(){
    const btn = document.querySelector('[data-compact-toggle]');
    if (!btn) return;
    btn.addEventListener('click', () => document.body.classList.toggle('compact'));
  }

  document.addEventListener('DOMContentLoaded', function(){
    enhanceDetail();
    enhanceList();
  });
})();
