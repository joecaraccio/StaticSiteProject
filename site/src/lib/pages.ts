/**
 * Reads the page documents the pipeline exported.
 *
 * The site's only input is `data/export/`: a manifest plus one JSON document per
 * page. Nothing here reaches for a database, which is what keeps the templates
 * testable and the build reproducible.
 */
import fs from "node:fs";
import path from "node:path";

export const PAGES_DIR =
  process.env.PAGES_DIR ?? path.resolve(process.cwd(), "..", "data", "export");

export type PageType = "flight" | "route" | "airport" | "airline";

export interface MonthPoint {
  month: string;
  ops_scheduled: number;
  ops_operated: number;
  on_time_rate: number | null;
  cancellation_rate: number | null;
}

export interface Alternative {
  carrier: string;
  flight_number: string;
  typical_sched_dep: string | null;
  ops_scheduled: number;
  on_time_rate: number | null;
  cancellation_rate: number | null;
  avg_arr_delay_when_late_min: number | null;
  is_this_page: boolean;
  url: string;
}

export interface PageDocument {
  schema_version: number;
  page_type: PageType;
  url: string;
  key: Record<string, string>;
  data_period: { start: string; end: string };
  source: { attribution: string; table?: string };
  generated_at: string;
  headline_stats: {
    ops_scheduled: number;
    ops_operated: number;
    ops_measurable: number;
    on_time_rate: number | null;
    cancellation_rate: number | null;
    diversion_rate: number | null;
    avg_arr_delay_min: number | null;
    avg_arr_delay_when_late_min: number | null;
    median_arr_delay_when_late_min: number | null;
    share_3h_plus: number | null;
  };
  coverage: { first_seen: string | null; last_seen: string | null; months_covered: number | null };
  monthly_series: MonthPoint[];
  delay_causes: {
    basis: string;
    total_minutes: number;
    minutes: Record<string, number>;
    shares: Record<string, number> | null;
  };
  delay_distribution: {
    counts: Record<string, number>;
    shares: Record<string, number> | null;
  };
  alternatives: Alternative[];
  summary: { sentences: string[]; matched_rules: string[] } | null;
  demo_notice: string | null;
  gate: {
    outcome: "publish" | "noindex";
    noindex: boolean;
    reasons: string[];
    skipped_gates: string[];
    redirect_hint: string | null;
  };
}

export interface ManifestEntry {
  url: string;
  page_type: PageType;
  file: string;
  outcome: "publish" | "noindex";
}

export interface Manifest {
  schema_version: number;
  generated_at: string;
  data_period: { start: string; end: string };
  source: { attribution: string };
  demo_notice: string | null;
  totals: Record<string, number>;
  by_page_type: Record<string, Record<string, number>>;
  pages: ManifestEntry[];
}

/** The schema this site knows how to render. A mismatch must fail the build. */
export const EXPECTED_SCHEMA_VERSION = 1;

export function readManifest(): Manifest | null {
  const file = path.join(PAGES_DIR, "manifest.json");
  if (!fs.existsSync(file)) return null;
  const manifest: Manifest = JSON.parse(fs.readFileSync(file, "utf8"));
  if (manifest.schema_version !== EXPECTED_SCHEMA_VERSION) {
    throw new Error(
      `Exported pages are schema version ${manifest.schema_version}, but this site ` +
        `renders version ${EXPECTED_SCHEMA_VERSION}. Re-run the export, or update the site.`,
    );
  }
  return manifest;
}

export function readPage(entry: ManifestEntry): PageDocument {
  return JSON.parse(fs.readFileSync(path.join(PAGES_DIR, entry.file), "utf8"));
}

/** Human title for a page, matching how someone would search for it. */
export function pageTitle(doc: PageDocument): string {
  const k = doc.key;
  switch (doc.page_type) {
    case "flight":
      return `${k.carrier} ${k.flight_number}: ${k.origin} to ${k.dest}`;
    case "route":
      return `${k.origin} to ${k.dest} flights`;
    case "airport":
      return `${k.airport} airport delays`;
    case "airline":
      return `${k.carrier} on-time performance`;
  }
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatMinutes(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value)} min`;
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-US");
}

/** "January 2024 – December 2024", for the data-period line every page carries. */
export function formatPeriod(period: { start: string; end: string }): string {
  const fmt = (iso: string) =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    });
  return `${fmt(period.start)} – ${fmt(period.end)}`;
}
