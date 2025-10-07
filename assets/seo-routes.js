// FILE: assets/seo-routes.js
(function () {
  // Map primary category slugs -> SEO-friendly path segment
  // Edit freely to suit your copy.
  const CATEGORY_ALIAS = {
    "hotels": "places-to-stay",
    "restaurants": "places-to-eat",
    "malls": "shopping-malls",
    "spas": "spas",
    "clinics": "clinics",
    "schools": "schools",
    // Add more when you need them
  };

  function slugify(s){
    return (s||"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,"");
  }

  function categoryToAlias(catNameOrSlug){
    const s = slugify(catNameOrSlug);
    return CATEGORY_ALIAS[s] || s;
  }

  function prettyCategoryUrl(siteUrl, catNameOrSlug){
    const alias = categoryToAlias(catNameOrSlug);
    return `${siteUrl.replace(/\/$/, "")}/${alias}/`;
  }

  function prettyItemUrl(siteUrl, catNameOrSlug, itemSlug){
    const alias = categoryToAlias(catNameOrSlug);
    return `${siteUrl.replace(/\/$/, "")}/${alias}/${itemSlug}/`;
  }

  // Expose globally for app.js/tool.js
  window.SEO_ROUTES = { categoryToAlias, prettyCategoryUrl, prettyItemUrl };
})();
