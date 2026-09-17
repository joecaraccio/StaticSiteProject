"""Command line entry point: `pipeline <command>` or `python -m pipeline <command>`.

Commands mirror the stages in the architecture diagram in docs/PLAN.md:

    verify-source   confirm the live BTS source and record what was seen
    ingest          download raw months, then normalize them to Parquet
    normalize       re-derive Parquet from raw already on disk
    build           (re)create the DuckDB metric views
    export          write one JSON document per page and run the quality gates
    status          what is on disk, and whether the source is verified
    query           run read-only SQL against the built database
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date

from pipeline import config, normalize
from pipeline.export import pages
from pipeline.metrics import build
from pipeline.sources import bts_ontime, verify


def _expand_months(tokens: Sequence[str]) -> list[tuple[int, int]]:
    """Expand `2025-01` and `2025-01..2025-06` into an ordered, de-duplicated list."""
    months: list[tuple[int, int]] = []
    for token in tokens:
        if ".." in token:
            start, end = token.split("..", 1)
            y0, m0 = bts_ontime.parse_month(start)
            y1, m1 = bts_ontime.parse_month(end)
            if (y1, m1) < (y0, m0):
                raise SystemExit(f"Month range runs backwards: {token}")
            y, m = y0, m0
            while (y, m) <= (y1, m1):
                months.append((y, m))
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        else:
            months.append(bts_ontime.parse_month(token))
    return sorted(dict.fromkeys(months))


# --- commands --------------------------------------------------------------


def cmd_verify_source(args: argparse.Namespace) -> int:
    try:
        record = verify.verify(args.month, force_download=args.force)
    except verify.NotVerified as exc:
        print(f"Verification failed.\n\n{exc}", file=sys.stderr)
        return 2

    print(f"Source verified against {record.url}")
    print(f"  CSV member:  {record.csv_member}")
    print(f"  Delimiter:   {record.delimiter!r}   Encoding: {record.encoding}")
    print(f"  Columns:     {len(record.header)} in source, {len(record.matched_columns)} mapped")
    if record.missing_required:
        print(f"  MISSING REQUIRED: {', '.join(record.missing_required)}")
    if record.missing_optional:
        print(f"  Missing optional: {', '.join(record.missing_optional)}")
    print(f"  Record:      {verify.record_path()}")

    notes = verify.as_markdown(record)
    if args.write_notes:
        with open(args.write_notes, "a") as fh:
            fh.write("\n" + notes)
        print(f"  Appended a DATA_NOTES block to {args.write_notes}")
    else:
        print("\n--- paste into docs/DATA_NOTES.md ---\n")
        print(notes)
    return 1 if record.missing_required else 0


def cmd_ingest(args: argparse.Namespace) -> int:
    try:
        record = verify.require_verified()
    except verify.NotVerified as exc:
        print(f"Refusing to ingest an unverified source.\n\n{exc}", file=sys.stderr)
        return 2

    for year, month in _expand_months(args.months):
        label = bts_ontime.month_label(year, month)
        raw = bts_ontime.fetch_month(
            year, month, url_template=record.url_template, force=args.force
        )
        print(f"{label}  {raw.outcome:<10} {raw.bytes:>12,} bytes  sha256 {raw.sha256[:12]}")
        if raw.outcome == "unchanged" and normalize.parquet_path(year, month).exists():
            print(f"{label}  parquet up to date, skipping normalize")
            continue
        result = normalize.normalize_month(year, month)
        print(f"{label}  normalized {result.written_rows:,} rows -> {result.parquet_path}")
    return 0


def cmd_normalize(args: argparse.Namespace) -> int:
    for year, month in _expand_months(args.months):
        result = normalize.normalize_month(year, month)
        print(
            f"{result.month}  {result.source_rows:,} source rows -> "
            f"{result.written_rows:,} rows, {result.columns} columns"
        )
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    try:
        views, summary = build.rebuild_database()
    except build.NoDataError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Built {len(views)} views in {config.PATHS.duckdb_file}")
    print(f"  rows:     {summary['rows']:,}")
    print(f"  months:   {summary['months']} ({summary['earliest']} .. {summary['latest']})")
    print(f"  carriers: {summary['carriers']}   routes: {summary['routes']:,}")
    if args.verbose:
        for view in views:
            print(f"  - {view}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    if not config.PATHS.duckdb_file.exists():
        print("No database yet. Run `pipeline build` first.", file=sys.stderr)
        return 2
    try:
        result = pages.export_all(today=args.today, demo_notice=args.demo_notice)
    except build.NoDataError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"Wrote {result.written:,} page documents, dropped {result.dropped:,}")
    for page_type, counts in sorted(result.by_type.items()):
        detail = "  ".join(f"{k}={v:,}" for k, v in counts.items())
        print(f"  {page_type:<9} {detail}")
    print(f"  gate report: {result.report_path}")
    print(f"  manifest:    {result.manifest_path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    paths = config.PATHS
    print(f"data root: {paths.root}")

    try:
        record = verify.require_verified()
        print(f"source:    verified {record.verified_at[:10]} against {record.url_template}")
    except verify.NotVerified as exc:
        print(f"source:    NOT VERIFIED - {str(exc).splitlines()[0]}")

    raw_months = sorted(p.stem for p in paths.raw.rglob("*.zip") if ".meta" not in p.stem)
    clean_months = normalize.available_months()
    print(f"raw:       {len(raw_months)} archives under {paths.raw}")
    print(
        f"clean:     {len(clean_months)} months"
        + (f" ({clean_months[0]} .. {clean_months[-1]})" if clean_months else "")
    )
    print(
        f"duckdb:    {'present' if paths.duckdb_file.exists() else 'absent'} at {paths.duckdb_file}"
    )

    missing = [m for m in clean_months if m not in raw_months and args.strict]
    if missing:
        print(f"warning:   clean months with no raw archive: {', '.join(missing)}")
    if args.json:
        print(
            json.dumps(
                {
                    "data_root": str(paths.root),
                    "raw_archives": len(raw_months),
                    "clean_months": clean_months,
                    "duckdb_present": paths.duckdb_file.exists(),
                    "checked_at": date.today().isoformat(),
                },
                indent=2,
            )
        )
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    if not config.PATHS.duckdb_file.exists():
        print("No database yet. Run `pipeline build` first.", file=sys.stderr)
        return 2
    con = build.connect(read_only=True)
    try:
        cursor = con.execute(args.sql)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
    finally:
        con.close()
    if args.format == "json":
        print(json.dumps([dict(zip(columns, r, strict=True)) for r in rows], indent=2, default=str))
    else:
        widths = [
            max(len(c), *(len(str(r[i])) for r in rows)) if rows else len(c)
            for i, c in enumerate(columns)
        ]
        print("  ".join(c.ljust(w) for c, w in zip(columns, widths, strict=True)))
        print("  ".join("-" * w for w in widths))
        for r in rows:
            print("  ".join(str(v).ljust(w) for v, w in zip(r, widths, strict=True)))
        print(f"\n{len(rows)} row(s)")
    return 0


# --- wiring ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("verify-source", help="confirm the live BTS source (needs network)")
    p.add_argument("--month", required=True, help="a month to check with, e.g. 2025-01")
    p.add_argument("--force", action="store_true", help="re-download even if cached")
    p.add_argument("--write-notes", metavar="PATH", help="append the result to a markdown file")
    p.set_defaults(func=cmd_verify_source)

    p = sub.add_parser("ingest", help="download and normalize months")
    p.add_argument(
        "--months", nargs="+", required=True, metavar="YYYY-MM", help="or YYYY-MM..YYYY-MM"
    )
    p.add_argument("--force", action="store_true", help="ignore cached checksums")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("normalize", help="re-derive Parquet from raw already on disk")
    p.add_argument("--months", nargs="+", required=True, metavar="YYYY-MM")
    p.set_defaults(func=cmd_normalize)

    p = sub.add_parser("build", help="(re)create the DuckDB metric views")
    p.add_argument("-v", "--verbose", action="store_true", help="list the views created")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("export", help="write page JSON and run the quality gates")
    p.add_argument(
        "--today",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="treat this as today's date when checking data age (for reproducible runs)",
    )
    p.add_argument(
        "--demo-notice",
        metavar="TEXT",
        help="stamp every page as synthetic (mockup builds only; forces noindex on the site)",
    )
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("status", help="what is on disk")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true", help="warn about clean months with no raw file")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("query", help="run read-only SQL against the built database")
    p.add_argument("sql")
    p.add_argument("--format", choices=("table", "json"), default="table")
    p.set_defaults(func=cmd_query)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
