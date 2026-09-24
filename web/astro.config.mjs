import { defineConfig } from "astro/config";
import react from "@astrojs/react";

// Static site producing flat HTML files (index.html, routes_map.html,
// port_dashboard.html) so URLs and relative links stay identical to the
// legacy hand-generated pages.
export default defineConfig({
  integrations: [react()],
  build: {
    format: "file",
  },
  vite: {
    // Relative asset paths keep dist/ openable via file:// and GitHub Pages.
    base: "./",
    // Large generated JSON payloads are inlined as JSON.parse("...") chunks.
    json: { stringify: true },
  },
});
