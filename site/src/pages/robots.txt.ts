/**
 * robots.txt, generated so the sitemap URL always matches the configured site.
 *
 * Per-page noindex is a meta tag on the page itself (see Base.astro): a gated
 * page must not be Disallow'd here, or crawlers never see the tag.
 */
import type { APIRoute } from "astro";

export const GET: APIRoute = ({ site }) => {
  const base = site?.href.replace(/\/$/, "") ?? "";
  return new Response(
    ["User-agent: *", "Allow: /", "", `Sitemap: ${base}/sitemap.xml`, ""].join("\n"),
    { headers: { "Content-Type": "text/plain; charset=utf-8" } },
  );
};
