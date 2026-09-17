import { defineConfig } from "astro/config";

export default defineConfig({
  // Mockup builds go to their own directory so they can never overwrite, or be
  // mistaken for, the real build (see scripts/make_mockup_data.py).
  outDir: process.env.OUT_DIR ?? "dist",
  // Set this to the real domain at M8; it feeds canonical tags and the sitemap.
  site: process.env.SITE_URL ?? "http://localhost:8081",
  // Directory-style URLs, so /routes/BOS-LGA/ works on any static host.
  build: { format: "directory" },
  // The site is static by design: it reads the pipeline's JSON at build time and
  // never queries a database (docs/PLAN.md §4).
  output: "static",
});
