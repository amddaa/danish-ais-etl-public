import { cpSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// Copy published verification plots from the Python analysis output into
// public/ so they are available on the dev server and included in dist/.
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const src = join(repoRoot, "source", "analysis", "ports", "output", "plots");
const dest = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "ports", "output", "plots");

if (!existsSync(src)) {
  console.warn(`[sync-plots] Plots not found at ${src} - skipping.`);
  process.exit(0);
}

mkdirSync(dest, { recursive: true });
for (const f of readdirSync(src)) {
  if (f.endsWith(".png")) {
    cpSync(join(src, f), join(dest, f));
  }
}
console.log(`[sync-plots] Copied plots to ${dest}`);
