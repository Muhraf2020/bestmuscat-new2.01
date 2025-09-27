/* app.enhanced.js — additive features; safe to include alongside your existing app.js */
(function () {
  // ---------- Utils ----------
  function escapeHTML(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function parseQuery() {
    const q = {};
    (location.search || "")
      .replace(/^\?/, "")
      .split("&")
      .forEach((kv) => {
        if (!kv) return;
        const [k, v] = kv.split("=");
        q[decodeURIComponent(k)] = decodeURIComponent((v || "").replace(/\+/g, " "));
      });
    return q;
  }

  async function loadJSON(path) {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) throw new Error("Failed to load " + path + " (" + r.status + ")");
    return r.json();
  }

  // Support both legacy hours {Mon:[["09:00","17:00"],...], ...}
  // and new hours {tz:"...", weekly:{mon:[{open:"09:00",close:"17:00"}], ...}}
  function getDaySlots(hours, now = new Date()) {
    if (!hours) return [];
    // weekly format
    if (hours.weekly && typeof hours.weekly === "object") {
      const daysLower = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
      const key = daysLower[now.getDay()];
      const arr = hours.weekly[key] || [];
      // Normalize to [["HH:MM","HH:MM"], ...]
      return arr
        .map((x) => {
          if (!x) return null;
          const o = x.open || (Array.isArray(x) ? x[0] : null);
          const c = x.close || (Array.isArray(x) ? x[1] : null);
          return o && c ? [o, c] : null;
        })
        .filter(Boolean);
    }
    // legacy format
    const daysTitle = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const key = daysTitle[now.getDay()];
    const slots = hours[key] || [];
    // Already [["HH:MM","HH:MM"], ...]
    return Array.isArray(slots) ? slots : [];
  }

  function isOpenNow(hours, now = new Date()) {
    try {
      const slots = getDaySlots(hours, now);
      const mins = now.getHours() * 60 + now.getMinutes();
      for (const [open, close] of slots) {
        const [oh, om] = String(open).split(":").map(Number);
        const [ch, cm] = String(close).split(":").map(Number);
        let o = oh * 60 + om,
          c = ch * 60 + cm;
        if (isNaN(o) || isNaN(c)) continue;
        if (c <= o) c += 24 * 60; // overnight
        let m = mins;
        if (m < o) m += 24 * 60;
        if (m >= o && m <= c) return true;
      }
      return false;
    } catch (e) {
      return false;
    }
  }

  function injectJSONLD(place) {
    // Build openingHoursSpecification from either format
    const openingHoursSpec = [];
    const dayMaps = [
      ["Sunday", "sun", "Sun"],
      ["Monday", "mon", "Mon"],
      ["Tuesday", "tue", "Tue"],
      ["Wednesday", "wed", "Wed"],
      ["Thursday", "thu", "Thu"],
      ["Friday", "fri", "Fri"],
      ["Saturday", "sat", "Sat"],
    ];
    if (place.hours) {
      // weekly
      if (place.hours.weekly) {
        for (const [dayName, keyLower] of dayMaps.map((d) => [d[0], d[1]])) {
          const slots = (place.hours.weekly[keyLower] || []).map((s) => [
            s.open,
            s.close,
          ]);
          slots.forEach(([o, c]) => {
            if (o && c) {
              openingHoursSpec.push({
                "@type": "OpeningHoursSpecification",
                dayOfWeek: dayName,
                opens: o,
                closes: c,
              });
            }
          });
        }
      } else {
        // legacy
        for (const [dayName, _lower, keyTitle] of dayMaps) {
          const slots = place.hours[keyTitle] || [];
          (Array.isArray(slots) ? slots : []).forEach(([o, c]) => {
            if (o && c) {
              openingHoursSpec.push({
                "@type": "OpeningHoursSpecification",
                dayOfWeek: dayName,
                opens: o,
                closes: c,
              });
            }
          });
        }
      }
    }

    const reviewBlock = place.public_reviews || place.public_sentiment || {};
    const ld = {
      "@context": "https://schema.org",
      "@type": "LocalBusiness",
      "name": place.name,
      "url": location.href,
      "address": place.location && place.location.address,
      "telephone": (place.actions && place.actions.phone) || undefined,
      "image": (place.gallery || [])[0] || (place.images && place.images.hero) || undefined,
      "aggregateRating": typeof place.rating_overall === "number" ? {
        "@type": "AggregateRating",
        "ratingValue": place.rating_overall,
        "reviewCount": reviewBlock.count || 0
      } : undefined,
      "openingHoursSpecification": openingHoursSpec,
      "servesCuisine": place.cuisines,
      "priceRange": place.price_range || undefined
    };

    const s = document.createElement("script");
    s.type = "application/ld+json";
    s.textContent = JSON.stringify(ld);
    document.head.appendChild(s);

    if ((place.faqs || []).length) {
      const faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": place.faqs.map((x) => ({
          "@type": "Question",
          "name": x.q,
          "acceptedAnswer": { "@type": "Answer", "text": x.a },
        })),
      };
      const s2 = document.createElement("script");
      s2.type = "application/ld+json";
      s2.textContent = JSON.stringify(faq);
      document.head.appendChild(s2);
    }
  }

  function renderDetailExtras(place) {
    const root =
      document.querySelector("#place-details") ||
      document.querySelector("[data-place-details]") ||
      document.querySelector("main") ||
      document.body;

    const wrap = document.createElement("section");
    wrap.className = "bm-extras";
    // --- Keep base sections hidden if there's no data; optionally fill them if there is ---
    const secCuisines = document.getElementById('cuisines');
    const secMeals    = document.getElementById('meals');
    const rootCuis    = document.getElementById('d-cuisines');
    const rootMeals   = document.getElementById('d-meals');
    
    // Hide when empty
    if (!Array.isArray(place.cuisines) || place.cuisines.length === 0) {
      secCuisines?.setAttribute('hidden','');
      if (rootCuis) rootCuis.innerHTML = '';
    }
    if (!Array.isArray(place.meals) || place.meals.length === 0) {
      secMeals?.setAttribute('hidden','');
      if (rootMeals) rootMeals.innerHTML = '';
    }
    
    // If data exists, (re)fill and unhide (safe if these sections exist in tool.html)
    if (Array.isArray(place.cuisines) && place.cuisines.length && secCuisines && rootCuis) {
      rootCuis.innerHTML = place.cuisines.map(v => `<span class="chip">${escapeHTML(v)}</span>`).join('');
      secCuisines.removeAttribute('hidden');
    }
    if (Array.isArray(place.meals) && place.meals.length && secMeals && rootMeals) {
      rootMeals.innerHTML = place.meals.map(v => `<span class="chip">${escapeHTML(v)}</span>`).join('');
      secMeals.removeAttribute('hidden');
    }


    // ---------- Top chips (price / busyness) ----------
    const chips = [];
    if (place.price_range) {
      chips.push(`<span class="chip">${escapeHTML(place.price_range)}</span>`);
    }
    if (place.busyness_hint) {
      chips.push(`<span class="chip">${escapeHTML(place.busyness_hint)}</span>`);
    }

    // ---------- Status (Open/Closed or —) ----------
    const openLabel = place.hours
      ? (isOpenNow(place.hours) ? "Open" : "Closed")
      : "—";
    const status =
      openLabel !== "—"
        ? `<span class="status badge">${openLabel}</span>`
        : "";

    // ---------- Header bits (overall rating) ----------
    const headerBits = [];
    if (typeof place.rating_overall === "number") {
      headerBits.push(
        `<div class="rating" title="Overall rating">${place.rating_overall.toFixed(
          2
        )}</div>`
      );
    }

    // ---------- Sections (subscores, reviews, about, amenities/cuisines/meals) ----------
    const sections = [];

    // Subscores
    if (place.subscores) {
      const kv = Object.entries(place.subscores).filter(
        ([, v]) => typeof v === "number"
      );
      if (kv.length) {
        sections.push(
          `<section class="subscores">
            ${kv
              .map(
                ([k, v]) =>
                  `<div class="row"><span>${escapeHTML(
                    k
                  )}</span><span>${v.toFixed(2)}</span></div>`
              )
              .join("")}
          </section>`
        );
      }
    }

    // Public reviews (new) or fallback to legacy public_sentiment
    const pr = place.public_reviews || null;
    const legacy = !pr && place.public_sentiment ? place.public_sentiment : null;
    if (pr || legacy) {
      const source = pr ? pr.source || "Reviews" : "Reviews";
      const count = pr ? pr.count : legacy.count;
      const insight = pr ? pr.insight : legacy.summary;
      const last_updated = pr ? pr.last_updated : legacy.last_updated;
      const cntStr =
        Number.isInteger(count) && count >= 0 ? `: ${count}` : "";
      const upd =
        last_updated ? `<div class="muted">Last updated ${escapeHTML(last_updated)}</div>` : "";
      const insightHTML = insight ? `<div>${escapeHTML(insight)}</div>` : "";
      sections.push(
        `<section class="reviews">
          <div class="muted">${escapeHTML(source)}${cntStr}</div>
          ${insightHTML}${upd}
        </section>`
      );
    }

    // About
    if (place.about && (place.about.short || place.about.long)) {
      sections.push(
        `<section class="about">
          ${
            place.about.short
              ? `<p class="lede">${escapeHTML(place.about.short)}</p>`
              : ""
          }
          ${
            place.about.long
              ? `<p>${escapeHTML(place.about.long)}</p>`
              : ""
          }
        </section>`
      );
    }

    // Amenities / Cuisines / Meals
    ["amenities", "cuisines", "meals"].forEach((key) => {
      if (Array.isArray(place[key]) && place[key].length) {
        sections.push(
          `<section class="${key}">
            <h3>${key[0].toUpperCase() + key.slice(1)}</h3>
            <div class="chips">
              ${place[key]
                .map((v) => `<span class="chip">${escapeHTML(v)}</span>`)
                .join("")}
            </div>
          </section>`
        );
      }
    });

    // ---------- CTA buttons (Menu) ----------
    const ctaButtons = [];
    if (place.actions && place.actions.menu) {
      ctaButtons.push(
        `<a class="btn" href="${escapeHTML(
          place.actions.menu
        )}" target="_blank" rel="noopener">Menu</a>`
      );
    }

    // ---------- Legacy content you had (cleaned: no duplicate Amenities) ----------
    const badges = (place.badges || [])
      .map((b) => `<span class="badge">${escapeHTML(b)}</span>`)
      .join(" ");
    const dishes = (place.dishes || [])
      .map((d) => `<li>${escapeHTML(d)}</li>`)
      .join("");
    const times = (place.best_times || [])
      .map(
        (t) =>
          `<li><strong>${escapeHTML(t.label || "")}:</strong> ${escapeHTML(
            t.window || ""
          )}</li>`
      )
      .join("");

    // ---------- Compose ----------
    wrap.innerHTML = `
      <div class="detail-top">
        <div class="chips">${status} ${chips.join(" ")}</div>
        <div class="header-bits">${headerBits.join("")}</div>
        <div class="cta-buttons">${ctaButtons.join(" ")}</div>
      </div>

      ${sections.join("")}

      <div class="extras-grid">
        <div>
          <h3>Badges</h3>
          <p>${badges || "—"}</p>
          <h3>Verified & Methodology</h3>
          <p>${place.verified ? "Verified" : "Unverified"}${
      place.methodology_note ? " — " + escapeHTML(place.methodology_note) : ""
    }</p>
          <h3>Best Times</h3>
          <ul>${times || "<li>—</li>"}</ul>
        </div>
        <div>
          <h3>Dishes</h3>
          <ul>${dishes || "<li>—</li>"}</ul>
          <h3>FAQs</h3>
          <ul>${
            (place.faqs || [])
              .map(
                (f) =>
                  `<li><strong>${escapeHTML(f.q)}</strong><br>${escapeHTML(
                    f.a
                  )}</li>`
              )
              .join("") || "<li>—</li>"
          }</ul>
        </div>
      </div>
    `;
    root.appendChild(wrap);
  }

  async function enhanceDetail() {
    const q = parseQuery();
    if (!q.slug) return;

    // Prefer new ingestion output (tools.json); fallback to old (places.json)
    let rows = null;
    try {
      rows = await loadJSON("data/tools.json?ts=" + Date.now());
    } catch (e) {
      rows = await loadJSON("data/places.json");
    }

    const place = Array.isArray(rows) ? rows.find((p) => p.slug === q.slug) : null;
    if (!place) return;

    injectJSONLD(place);
    renderDetailExtras(place);
  }

  // Compact list toggle (if container present)
  function enhanceList() {
    const btn = document.querySelector("[data-compact-toggle]");
    if (!btn) return;
    btn.addEventListener("click", () =>
      document.body.classList.toggle("compact")
    );
  }

  document.addEventListener("DOMContentLoaded", function () {
    enhanceDetail();
    enhanceList();
  });
})();
