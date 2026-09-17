/**
 * Sitemap of published pages only.
 *
 * Pages the gates marked `noindex` are deliberately excluded: submitting a page
 * we are asking not to be indexed wastes crawl budget. PLAN.md §9 calls for one
 * sitemap per page type behind an index once volumes grow past ~50,000 URLs;
 * until then a single file is correct and simpler.
 */
import type { APIRoute } from "astro";
import { readManifest } from "../lib/pages";

export const GET: APIRoute = ({ site }) => {
  const base = site?.href.replace(/\/$/, "") ?? "";
  const manifest = readManifest();
  const urls = (manifest?.pages ?? [])
    .filter((p) => p.outcome === "publish")
    .map((p) => `  <url><loc>${base}${p.url}</loc></url>`);

  const body = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    `  <url><loc>${base}/</loc></url>`,
    ...urls,
    "</urlset>",
    "",
  ].join("\n");

  return new Response(body, { headers: { "Content-Type": "application/xml; charset=utf-8" } });
};
