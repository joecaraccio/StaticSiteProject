"""Export one JSON document per page, then run every page through the gates.

The site never queries the database (docs/PLAN.md §4): it reads these files. That
keeps the site dumb and testable, and it means a page's contents can be diffed.

Schema version lives in every document. Bump it when a field's meaning changes,
so a stale site build fails loudly instead of rendering the wrong thing.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb

from pipeline import config
from pipeline.gates.rules import Decision, Outcome, PageCandidate, evaluate, report_rows, summarize
from pipeline.metrics import build

SCHEMA_VERSION = 1

ATTRIBUTION = "U.S. Department of Transportation, Bureau of Transportation Statistics"

#: page type -> (view, key columns, URL pattern)
PAGE_TYPES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "flight": (
        "flight_metrics",
        ("carrier", "flight_number", "origin", "dest"),
        "/flights/{carrier}/{flight_number}/{origin}-{dest}",
    ),
    "route": ("route_metrics", ("origin", "dest"), "/routes/{origin}-{dest}"),
    "airport": ("airport_metrics", ("airport", "role"), "/airports/{airport}"),
    "airline": ("airline_metrics", ("carrier",), "/airlines/{carrier}"),
}

#: Blocks docs/PLAN.md §7 requires on every page. A block that comes back without
#: real data fails the gate rather than rendering empty.
REQUIRED_BLOCKS = ("headline_stats", "monthly_series", "delay_causes", "delay_distribution")


@dataclass
class ExportResult:
    written: int
    dropped: int
    by_type: dict[str, dict[str, int]]
    report_path: str
    manifest_path: str


def _data_period(con: duckdb.DuckDBPyConnection) -> tuple[date, date]:
    start, end = con.execute("SELECT min(flight_date), max(flight_date) FROM operations").fetchone()
    return start, end


def _rows(con: duckdb.DuckDBPyConnection, view: str) -> list[dict[str, Any]]:
    cursor = con.execute(f"SELECT * FROM {view}")  # view names are from PAGE_TYPES
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]


def _monthly_series(con: duckdb.DuckDBPyConnection, view: str, keys: dict[str, Any]) -> list[dict]:
    where = " AND ".join(f"{k} = ?" for k in keys)
    cursor = con.execute(
        f"SELECT strftime(flight_month, '%Y-%m') AS month, ops_scheduled, ops_operated, "
        f"on_time_rate, cancellation_rate FROM {view} WHERE {where} ORDER BY month",
        list(keys.values()),
    )
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]


def _delay_causes(row: dict[str, Any]) -> dict[str, Any]:
    """Cause shares, as a fraction of *attributed* minutes.

    BTS populates cause columns only for qualifying delays, so these are not
    shares of all delay minutes. The page must say so.
    """
    total = row.get("attributed_delay_min")
    total = 0 if total is None else total
    causes = {
        "carrier": row.get("carrier_delay_min") or 0,
        "weather": row.get("weather_delay_min") or 0,
        "nas": row.get("nas_delay_min") or 0,
        "security": row.get("security_delay_min") or 0,
        "late_aircraft": row.get("late_aircraft_delay_min") or 0,
    }
    return {
        "basis": "attributed_delay_minutes",
        "total_minutes": total,
        "minutes": causes,
        "shares": ({k: v / total for k, v in causes.items()} if total else None),
    }


def _delay_distribution(row: dict[str, Any]) -> dict[str, Any]:
    buckets = {
        "on_time": row.get("bucket_on_time") or 0,
        "d15_30": row.get("bucket_15_30") or 0,
        "d30_60": row.get("bucket_30_60") or 0,
        "d60_120": row.get("bucket_60_120") or 0,
        "d120_180": row.get("bucket_120_180") or 0,
        "d180_plus": row.get("bucket_180_plus") or 0,
        "cancelled_or_diverted": row.get("bucket_cancelled_diverted") or 0,
    }
    total = sum(buckets.values())
    return {
        "counts": buckets,
        "shares": ({k: v / total for k, v in buckets.items()} if total else None),
    }


def _missing_blocks(document: dict[str, Any]) -> tuple[str, ...]:
    """Which required blocks came back without usable data."""
    missing = []
    if document["headline_stats"].get("on_time_rate") is None:
        missing.append("headline_stats")
    if not document["monthly_series"]:
        missing.append("monthly_series")
    # A total of zero attributed minutes is real data - an entity with no
    # qualifying delays - so only a genuinely absent total counts as missing.
    # Pages must handle `shares: null` by saying there were no attributed delays.
    if document["delay_causes"]["total_minutes"] is None:
        missing.append("delay_causes")
    if document["delay_distribution"]["shares"] is None:
        missing.append("delay_distribution")
    return tuple(missing)


def _build_document(
    page_type: str,
    row: dict[str, Any],
    keys: dict[str, Any],
    url: str,
    monthly: list[dict],
    period: tuple[date, date],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "page_type": page_type,
        "url": url,
        "key": keys,
        "data_period": {"start": period[0].isoformat(), "end": period[1].isoformat()},
        "source": {
            "attribution": ATTRIBUTION,
            "table": "Airline On-Time Performance (reporting carrier)",
        },
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "headline_stats": {
            "ops_scheduled": row["ops_scheduled"],
            "ops_operated": row["ops_operated"],
            "ops_measurable": row["ops_measurable"],
            "on_time_rate": row["on_time_rate"],
            "cancellation_rate": row["cancellation_rate"],
            "diversion_rate": row["diversion_rate"],
            "avg_arr_delay_min": row["avg_arr_delay_min"],
            "avg_arr_delay_when_late_min": row["avg_arr_delay_when_late_min"],
            "median_arr_delay_when_late_min": row["median_arr_delay_when_late_min"],
            "share_3h_plus": row["share_3h_plus"],
        },
        "coverage": {
            "first_seen": row["first_seen"].isoformat() if row.get("first_seen") else None,
            "last_seen": row["last_seen"].isoformat() if row.get("last_seen") else None,
            "months_covered": row.get("months_covered"),
        },
        "monthly_series": monthly,
        "delay_causes": _delay_causes(row),
        "delay_distribution": _delay_distribution(row),
        # Filled in by the rule engine in M6. Present as null so the site's shape
        # does not change when it arrives.
        "summary": None,
    }


MONTHLY_VIEW = {
    "flight": "flight_by_month",
    "route": "route_by_month",
    "airport": "airport_by_month",
    "airline": "airline_by_month",
}


def export_all(
    con: duckdb.DuckDBPyConnection | None = None,
    *,
    today: date | None = None,
) -> ExportResult:
    """Export every candidate page, gate it, and write the report.

    `today` is injectable so an export is reproducible: the data-age gate is the
    one rule that depends on wall-clock time.
    """
    config.PATHS.ensure()
    owns = con is None
    con = con or build.connect(read_only=True)
    try:
        period = _data_period(con)
        if period[0] is None:
            raise build.NoDataError("No operations in the database; run ingest first.")

        decisions: dict[str, Decision] = {}
        by_type: dict[str, dict[str, int]] = {}
        manifest: list[dict[str, Any]] = []
        written = 0

        for page_type, (view, key_columns, url_pattern) in PAGE_TYPES.items():
            # Airport pages are keyed on the airport; the arrival/departure split
            # is a section within one page, so only departures drive the URL.
            rows = _rows(con, view)
            if page_type == "airport":
                rows = [r for r in rows if r["role"] == "departure"]

            for row in rows:
                keys = {k: row[k] for k in key_columns}
                url = url_pattern.format(**{k: str(v) for k, v in keys.items()})
                monthly = _monthly_series(con, MONTHLY_VIEW[page_type], keys)
                document = _build_document(page_type, row, keys, url, monthly, period)

                candidate = PageCandidate(
                    page_type=page_type,
                    key=url,
                    ops_t12=row["ops_scheduled"],
                    last_seen=row.get("last_seen"),
                    data_period_end=period[1],
                    missing_blocks=_missing_blocks(document),
                    is_reporting_carrier=page_type == "airline",
                )
                decision = evaluate(candidate, today=today)
                decisions[url] = decision
                counts = by_type.setdefault(page_type, dict.fromkeys((o.value for o in Outcome), 0))
                counts[decision.outcome.value] += 1

                if decision.outcome is Outcome.DROP:
                    continue

                document["gate"] = {
                    "outcome": decision.outcome.value,
                    "noindex": decision.outcome is Outcome.NOINDEX,
                    "reasons": decision.reasons,
                    "skipped_gates": decision.skipped,
                    "redirect_hint": decision.redirect_hint,
                }
                path = _write_document(url, document)
                manifest.append(
                    {
                        "url": url,
                        "page_type": page_type,
                        "file": path,
                        "outcome": decision.outcome.value,
                    }
                )
                written += 1

        report_path = _write_report(decisions)
        manifest_path = _write_manifest(manifest, period, summarize(decisions), by_type)
        return ExportResult(
            written=written,
            dropped=summarize(decisions)["drop"],
            by_type=by_type,
            report_path=report_path,
            manifest_path=manifest_path,
        )
    finally:
        if owns:
            con.close()


def _write_document(url: str, document: dict[str, Any]) -> str:
    """Write one page as `<export>/pages/<url>.json`."""
    relative = Path(url.strip("/") + ".json")
    path = config.PATHS.export / "pages" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, default=str) + "\n")
    return str(path.relative_to(config.PATHS.export))


def _write_report(decisions: dict[str, Decision]) -> str:
    path = config.PATHS.export / "gate_report.csv"
    rows = report_rows(decisions)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["key", "outcome", "redirect_hint", "reasons", "skipped_gates"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def _write_manifest(
    manifest: list[dict[str, Any]],
    period: tuple[date, date],
    totals: dict[str, int],
    by_type: dict[str, dict[str, int]],
) -> str:
    path = config.PATHS.export / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "data_period": {"start": period[0].isoformat(), "end": period[1].isoformat()},
                "source": {"attribution": ATTRIBUTION},
                "totals": totals,
                "by_page_type": by_type,
                "pages": manifest,
            },
            indent=2,
        )
        + "\n"
    )
    return str(path)
