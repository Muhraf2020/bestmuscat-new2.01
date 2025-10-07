// FILE: assets/seo-routes.js
(function () {
  // Map your internal category slugs -> SEO-friendly path segments
  // (Left side = what's in your data; Right side = folder/URL segment)
  const CATEGORY_ALIAS = {
    "hotels": "places-to-stay",
    "restaurants": "places-to-eat",
    "schools": "schools",
    "spas": "spas",
    "clinics": "clinics",
    "malls": "shopping-malls",
    "car-repair-garages": "car-repair-garages",
    "home-maintenance-and-repair": "home-maintenance-and-repair",
    "catering-services": "catering-services",
    "events": "events-planning",            // your UI uses slug "events"
    "events-planning": "events-planning",   // support either spelling just in case
    "moving-and-storage": "moving-and-storage"
  };

  function slugify(s){
    return (s||"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,"");
  }

  function categoryToAlias(catNameOrSlug){
    const s = slugify(catNameOrSlug);
    return CATEGORY_ALIAS[s] || s; // fall back to the slug if not mapped
  }

  function prettyCategoryUrl(siteUrl, catNameOrSlug){
    const alias = categoryToAlias(catNameOrSlug);
    return `${String(siteUrl).replace(/\/$/, "")}/${alias}/`;
  }

  function prettyItemUrl(siteUrl, catNameOrSlug, itemSlug){
    const alias = categoryToAlias(catNameOrSlug);
    return `${String(siteUrl).replace(/\/$/, "")}/${alias}/${itemSlug}/`;
  }

  window.SEO_ROUTES = { categoryToAlias, prettyCategoryUrl, prettyItemUrl };
})();
