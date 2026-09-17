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
from pipeline.summaries.rules import SummaryContext
from pipeline.summaries.rules import summarize as summarize_page

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
REQUIRED_BLOCKS = (
    "headline_stats",
    "monthly_series",
    "delay_causes",
    "delay_distribution",
    "alternatives",
)

#: How many alternatives to carry on a page. Long enough to be useful, short
#: enough that the page is not a database dump.
MAX_ALTERNATIVES = 12


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


def _rows(
    con: duckdb.DuckDBPyConnection, view: str, key_columns: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Every row of a metrics view, in a stable order.

    The ORDER BY is not cosmetic. DuckDB's GROUP BY gives no ordering guarantee,
    so without it two exports of identical data emit pages in different orders and
    the manifest churns. An export should be reproducible.
    """
    order = ", ".join(key_columns)
    # View and column names come from PAGE_TYPES, not from user input.
    cursor = con.execute(f"SELECT * FROM {view} ORDER BY {order}")
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


def _alternatives(
    con: duckdb.DuckDBPyConnection,
    page_type: str,
    keys: dict[str, Any],
) -> list[dict[str, Any]]:
    """The other flights a traveller could book instead, best on-time first.

    This is the "comparison with alternatives" block PLAN.md section 7 requires.
    Only flight and route pages have a meaningful set: an airport or airline page
    has no single alternative to compare against.

    The page's own flight is included and marked, so a reader can see where it
    sits rather than having to hold it in their head.
    """
    if page_type not in ("flight", "route"):
        return []

    cursor = con.execute(
        """
        SELECT carrier, flight_number, typical_sched_dep, ops_scheduled,
               on_time_rate, cancellation_rate, avg_arr_delay_when_late_min
        FROM flight_metrics
        WHERE origin = ? AND dest = ?
        ORDER BY on_time_rate DESC NULLS LAST, ops_scheduled DESC
        LIMIT ?
        """,
        [keys["origin"], keys["dest"], MAX_ALTERNATIVES],
    )
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]

    for row in rows:
        row["is_this_page"] = (
            page_type == "flight"
            and row["carrier"] == keys.get("carrier")
            and row["flight_number"] == keys.get("flight_number")
        )
        row["url"] = (
            f"/flights/{row['carrier']}/{row['flight_number']}/{keys['origin']}-{keys['dest']}"
        )
    return rows


#: How a page's subject is phrased in summary sentences.
def _subject(page_type: str, keys: dict[str, Any]) -> str:
    match page_type:
        case "flight":
            return f"{keys['carrier']} {keys['flight_number']}"
        case "route":
            return f"The {keys['origin']} to {keys['dest']} route"
        case "airport":
            return f"Departures from {keys['airport']}"
        case "airline":
            return f"{keys['carrier']}"
    return page_type


def _summary_context(
    page_type: str,
    row: dict[str, Any],
    keys: dict[str, Any],
    monthly: list[dict],
    alternatives: list[dict[str, Any]],
    peer_rate: float | None,
) -> SummaryContext:
    """Assemble what the summary rules are allowed to see.

    The rules phrase numbers; they never compute them. Everything here comes from
    the metrics layer or from the alternatives already gathered for the page.
    """
    best = None
    if page_type == "flight" and alternatives:
        top = alternatives[0]
        if not top["is_this_page"] and top["on_time_rate"] is not None:
            best = (f"{top['carrier']} {top['flight_number']}", top["on_time_rate"])

    peer_label = None
    if page_type == "flight":
        peer_label = f"the {keys['origin']} to {keys['dest']} route"

    return SummaryContext(
        page_type=page_type,
        subject=_subject(page_type, keys),
        ops_scheduled=row["ops_scheduled"],
        ops_measurable=row["ops_measurable"],
        on_time_rate=row["on_time_rate"],
        cancellation_rate=row["cancellation_rate"],
        avg_arr_delay_when_late_min=row["avg_arr_delay_when_late_min"],
        share_3h_plus=row["share_3h_plus"],
        monthly=tuple(
            (m["month"], m["on_time_rate"]) for m in monthly if m["on_time_rate"] is not None
        ),
        peer_rate=peer_rate if page_type == "flight" else None,
        peer_label=peer_label,
        best_alternative=best,
    )


def _route_rates(con: duckdb.DuckDBPyConnection) -> dict[tuple[str, str], float]:
    """Route-level on-time rates, so a flight page can say how it compares."""
    return {
        (origin, dest): rate
        for origin, dest, rate in con.execute(
            "SELECT origin, dest, on_time_rate FROM route_metrics"
        ).fetchall()
    }


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
    # Only flight and route pages carry alternatives, so an empty list is only a
    # failure where the block is supposed to exist.
    if document["page_type"] in ("flight", "route") and not document["alternatives"]:
        missing.append("alternatives")
    return tuple(missing)


def _build_document(
    page_type: str,
    row: dict[str, Any],
    keys: dict[str, Any],
    url: str,
    monthly: list[dict],
    alternatives: list[dict[str, Any]],
    period: tuple[date, date],
    generated_at: datetime,
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
        "generated_at": generated_at.isoformat(timespec="seconds"),
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
        "alternatives": alternatives,
        "delay_causes": _delay_causes(row),
        "delay_distribution": _delay_distribution(row),
        # Replaced by the rule engine's output in export_all.
        "summary": None,
        # Non-null only for synthetic mockup builds; see scripts/make_mockup_data.py.
        "demo_notice": None,
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
    demo_notice: str | None = None,
    generated_at: datetime | None = None,
) -> ExportResult:
    """Export every candidate page, gate it, and write the report.

    `today` is injectable so an export is reproducible: the data-age gate is the
    one rule that depends on wall-clock time.

    `generated_at` pins the timestamp written into every document. Left as None it
    is the wall clock, which is what a real run wants. The mockup pins it so that
    regenerating the committed synthetic export produces no diff unless the
    pipeline's actual output changed.

    `demo_notice` stamps every document and the manifest with a warning that the
    figures are synthetic. The site renders it as a persistent banner and forces
    `noindex`, so a mockup build cannot be mistaken for, or published as, the real
    thing. It is None for every real export.
    """
    config.PATHS.ensure()
    owns = con is None
    con = con or build.connect(read_only=True)
    try:
        period = _data_period(con)
        if period[0] is None:
            raise build.NoDataError("No operations in the database; run ingest first.")
        route_rates = _route_rates(con)
        stamp = generated_at or datetime.now().astimezone()

        decisions: dict[str, Decision] = {}
        by_type: dict[str, dict[str, int]] = {}
        manifest: list[dict[str, Any]] = []
        written = 0

        for page_type, (view, key_columns, url_pattern) in PAGE_TYPES.items():
            # Airport pages are keyed on the airport; the arrival/departure split
            # is a section within one page, so only departures drive the URL.
            rows = _rows(con, view, key_columns)
            if page_type == "airport":
                rows = [r for r in rows if r["role"] == "departure"]

            for row in rows:
                keys = {k: row[k] for k in key_columns}
                url = url_pattern.format(**{k: str(v) for k, v in keys.items()})
                monthly = _monthly_series(con, MONTHLY_VIEW[page_type], keys)
                alternatives = _alternatives(con, page_type, keys)
                document = _build_document(
                    page_type, row, keys, url, monthly, alternatives, period, stamp
                )
                if demo_notice:
                    document["demo_notice"] = demo_notice

                summary = summarize_page(
                    _summary_context(
                        page_type,
                        row,
                        keys,
                        monthly,
                        alternatives,
                        route_rates.get((keys.get("origin"), keys.get("dest"))),
                    )
                )
                document["summary"] = {
                    "sentences": summary.sentences,
                    "matched_rules": summary.matched_rules,
                }

                candidate = PageCandidate(
                    page_type=page_type,
                    key=url,
                    ops_t12=row["ops_scheduled"],
                    last_seen=row.get("last_seen"),
                    data_period_end=period[1],
                    missing_blocks=_missing_blocks(document),
                    summary_rules_matched=len(summary),
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
        manifest_path = _write_manifest(
            manifest, period, summarize(decisions), by_type, demo_notice, stamp
        )
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
    demo_notice: str | None = None,
    generated_at: datetime | None = None,
) -> str:
    path = config.PATHS.export / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "generated_at": generated_at.isoformat(timespec="seconds"),
                "data_period": {"start": period[0].isoformat(), "end": period[1].isoformat()},
                "source": {"attribution": ATTRIBUTION},
                "demo_notice": demo_notice,
                "totals": totals,
                "by_page_type": by_type,
                "pages": sorted(manifest, key=lambda entry: entry["url"]),
            },
            indent=2,
        )
        + "\n"
    )
    return str(path)
