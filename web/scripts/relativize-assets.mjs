import { readdirSync, readFileSync, writeFileSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// Astro emits root-absolute "/./_astro/..." (or "/_astro/...") when base is "./".
// Rewrite to true relative URLs so GitHub Pages project sites and file:// work.

const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");

function walk(dir, acc = [], exts = [".html"]) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, acc, exts);
    else if (exts.some((ext) => name.endsWith(ext))) acc.push(p);
  }
  return acc;
}

const files = walk(dist, [], [".html"]);
let changed = 0;
for (const file of files) {
  const src = readFileSync(file, "utf8");
  const next = src
    .replaceAll('"/./_astro/', '"./_astro/')
    .replaceAll("'././_astro/", "'./_astro/")
    .replaceAll('href="/./_astro/', 'href="./_astro/')
    .replaceAll('src="/./_astro/', 'src="./_astro/')
    .replaceAll('href="/_astro/', 'href="./_astro/')
    .replaceAll('src="/_astro/', 'src="./_astro/')
    .replaceAll('component-url="/./_astro/', 'component-url="./_astro/')
    .replaceAll('renderer-url="/./_astro/', 'renderer-url="./_astro/')
    .replaceAll('component-url="/_astro/', 'component-url="./_astro/')
    .replaceAll('renderer-url="/_astro/', 'renderer-url="./_astro/');
  if (next !== src) {
    writeFileSync(file, next);
    changed++;
  }
}
console.log(`[relativize-assets] Updated ${changed}/${files.length} HTML files`);

// Vite's preload helper uses origin-absolute "/"+path which 404s on GitHub Pages
// project sites. Rewrite to site-relative "./"+path (same folder as the HTML).
// Do not rewrite "/_astro/" strings in JS to "./_astro/" — JSON `?url` imports
// are resolved with import.meta.url from chunks inside _astro/.
const jsFiles = walk(join(dist, "_astro"), [], [".js"]);
let jsChanged = 0;
for (const file of jsFiles) {
  const src = readFileSync(file, "utf8");
  if (!src.includes("__vite__mapDeps")) continue;
  const next = src.replaceAll('function(i){return"/"+i}', 'function(i){return"./"+i}');
  if (next !== src) {
    writeFileSync(file, next);
    jsChanged++;
  }
}
console.log(`[relativize-assets] Patched ${jsChanged} JS preload helpers`);
