import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { execSync } from "child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// --- CONFIG ---
const BASE_URL = process.env.BASE_URL || "https://academiawithai.com/";
const SITE_ROOT = path.resolve(__dirname, "..");
const DATA_FILE = path.join(SITE_ROOT, "data", "tools.json");
const CATEGORY_DIR = path.join(SITE_ROOT, "category");
const OUTPUT_SITEMAP = path.join(SITE_ROOT, "sitemap.xml");
const OUTPUT_ROBOTS = path.join(SITE_ROOT, "robots.txt");

// Ensure trailing slash on BASE_URL
const base = BASE_URL.endsWith("/") ? BASE_URL : BASE_URL + "/";

// --- helpers ---
const exists = (p) => {
  try { fs.accessSync(p, fs.constants.F_OK); return true; } catch { return false; }
};
const today = () => new Date().toISOString().slice(0, 10);

// Best-effort: get last commit date (YYYY-MM-DD) for a path; fallback = today
function gitLastMod(absolutePath) {
  try {
    const cmd = `git log -1 --format=%cs -- "${absolutePath}"`;
    const out = execSync(cmd, { cwd: SITE_ROOT, stdio: ["ignore", "pipe", "ignore"] })
      .toString().trim();
    if (out) return out;
  } catch {}
  return today();
}

// --- collect URLs ---
const urls = [];

// Homepage
const homeFile = path.join(SITE_ROOT, "index.html");
if (exists(homeFile)) {
  urls.push({ loc: base + "index.html", lastmod: gitLastMod(homeFile) });
}

// Category pages: only add files that actually exist
if (exists(CATEGORY_DIR)) {
  const catFiles = fs.readdirSync(CATEGORY_DIR).filter(f => f.toLowerCase().endsWith(".html"));
  for (const f of catFiles) {
    const abs = path.join(CATEGORY_DIR, f);
    urls.push({
      loc: base + "category/" + encodeURI(f),
      lastmod: gitLastMod(abs),
    });
  }
}

// Tool detail pages from data/tools.json (slug-based)
let tools = [];
try {
  const json = JSON.parse(fs.readFileSync(DATA_FILE, "utf8"));
  tools = Array.isArray(json) ? json : (Array.isArray(json.tools) ? json.tools : []);
} catch (e) {
  console.warn("WARN: Could not read data/tools.json, skipping tool URLs.", e.message);
}

for (const t of tools) {
  if (!t || !t.slug) continue;
  // Use tool.html as the modified file for lastmod (best-effort)
  const toolTpl = path.join(SITE_ROOT, "tool.html");
  urls.push({
    loc: `${base}tool.html?slug=${encodeURIComponent(t.slug)}`,
    lastmod: exists(toolTpl) ? gitLastMod(toolTpl) : today(),
  });
}

// --- write sitemap.xml ---
const xmlHeader = `<?xml version="1.0" encoding="UTF-8"?>`;
const urlsetOpen = `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">`;
const urlsetClose = `</urlset>`;
const body = urls.map(u => {
  return `  <url>
    <loc>${u.loc}</loc>
    <lastmod>${u.lastmod}</lastmod>
  </url>`;
}).join("\n");

const xml = `${xmlHeader}\n${urlsetOpen}\n${body}\n${urlsetClose}\n`;
fs.writeFileSync(OUTPUT_SITEMAP, xml, "utf8");
console.log(`Wrote ${OUTPUT_SITEMAP} with ${urls.length} URLs`);

// --- write robots.txt ---
const robots = `User-agent: *
Allow: /

Sitemap: ${base}sitemap.xml
`;
fs.writeFileSync(OUTPUT_ROBOTS, robots, "utf8");
console.log(`Wrote ${OUTPUT_ROBOTS}`);
