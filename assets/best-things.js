/* FILE: assets/best-things.js
 * Loads cards for the “Best Things to Do in Muscat” section from assets/best-things.json
 * and renders them into #category-content based on the active tab.
 */

(function () {
  const BEST_THINGS_JSON_URL = "assets/best-things.json";

  // Map JSON category -> tab data-cat (must match your button data-cat values)
  const CAT_MAP = {
    "Tours & Experiences": "tours",
    "Events and Venues": "events",
    "Wellness & Aesthetics": "wellness"
  };

  function createCard(item) {
    const a = document.createElement("a");
    a.className = "card";
    a.href = item.url || "#";
    a.target = "_blank";
    a.rel = "noopener";

    const img = document.createElement("img");
    img.loading = "lazy";
    img.decoding = "async";
    img.alt = item.title || "";
    img.src = item.image_url || "assets/placeholders/placeholder-16x9.webp";
    img.onerror = () => { img.src = "assets/placeholders/placeholder-16x9.webp"; };

    const body = document.createElement("div");
    body.className = "card-body";

    const h3 = document.createElement("h3");
    h3.className = "card-title";
    h3.textContent = item.title || "";

    const p = document.createElement("p");
    p.className = "card-subtitle";
    p.textContent = item.subtitle || "";

    body.appendChild(h3);
    if (p.textContent) body.appendChild(p);

    a.appendChild(img);
    a.appendChild(body);
    return a;
  }

  function renderCategory(catKey, items) {
    const container = document.getElementById("category-content");
    if (!container) return;
    container.innerHTML = "";

    const grid = document.createElement("div");
    grid.className = "cards-grid";

    (items || []).forEach(item => grid.appendChild(createCard(item)));
    container.appendChild(grid);
  }

  function setActiveTab(catKey) {
    document.querySelectorAll("#best-things .tabs .tab").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.cat === catKey);
    });
  }

  function initTabs(byKey) {
    document.querySelectorAll("#best-things .tabs .tab").forEach(btn => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.cat;
        setActiveTab(key);
        renderCategory(key, byKey.get(key) || []);
      });
    });
  }

  async function loadAndRender() {
    try {
      // Cache-bust GH Pages/CDN
      const res = await fetch(`${BEST_THINGS_JSON_URL}?_=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      // Group items by our tab keys via CAT_MAP
      const byKey = new Map();
      (data || []).forEach(row => {
        const mapped = CAT_MAP[(row.category || "").trim()];
        if (!mapped) return;
        if (!byKey.has(mapped)) byKey.set(mapped, []);
        byKey.get(mapped).push(row);
      });

      initTabs(byKey);

      // Render initial active tab (so content shows without clicking)
      const active = document.querySelector("#best-things .tabs .tab.active");
      const initialKey = active?.dataset?.cat || "tours";
      setActiveTab(initialKey);
      renderCategory(initialKey, byKey.get(initialKey) || []);
    } catch (err) {
      console.error("Best Things loader failed:", err);
      const container = document.getElementById("category-content");
      if (container) container.innerHTML = "<p>Content unavailable. Please try again soon.</p>";
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    // Only run on pages that have the section
    if (document.getElementById("best-things")) loadAndRender();
  });
})();
