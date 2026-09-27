/**
 * Browser-side search: the matcher shared by the homepage dropdown and /search.
 *
 * Runs in the browser, so nothing here may import Node modules. The index is
 * built at build time by `searchEntries()` in `pages.ts` and embedded in the page
 * as JSON by `SearchBox.astro`, once per page however many scripts read it.
 */

/**
 * One searchable page, as compact tuples rather than objects: this ships inline
 * in the HTML, and across every page the difference is a few KB.
 * [haystack, url, title, type, band ("" if none), on-time rate (-1 if none), flights]
 */
export type IndexRow = [string, string, string, string, string, number, number];

export const TYPE_LABEL: Record<string, string> = {
  flight: "Flight",
  route: "Route",
  airport: "Airport",
  airline: "Airline",
};

export const BAND_LABEL: Record<string, string> = {
  good: "usually on time",
  warning: "mostly on time",
  serious: "often late",
  critical: "usually late",
};

// Routes and airports are what people search for; a flight number is the
// narrow case. Ranking by type keeps the useful answer at the top.
const TYPE_RANK: Record<string, number> = { route: 0, airport: 1, airline: 2, flight: 3 };

/** Every row whose haystack contains all the query's terms, best answer first. */
export function match(index: IndexRow[], query: string): IndexRow[] {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return [];
  return index
    .filter(([hay]) => terms.every((t) => hay.includes(t)))
    .sort((a, b) => TYPE_RANK[a[3]] - TYPE_RANK[b[3]] || b[5] - a[5]);
}

/** The index `SearchBox.astro` embedded in this page, or [] if there is none. */
export function readIndex(): IndexRow[] {
  const el = document.getElementById("search-index");
  return el?.textContent ? JSON.parse(el.textContent) : [];
}

export const escapeHtml = (value: unknown): string =>
  String(value).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
