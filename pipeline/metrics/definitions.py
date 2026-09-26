"""The metric definitions, written once.

Every grouped view (flight, route, airport, airline) is built from the same
expression list, so "on-time %" cannot mean one thing on a route page and
something else on an airport page.

Definitions follow CLAUDE.md exactly:
  * on time      - arr_del15 = 0, among flights that operated
  * operated     - not cancelled and not diverted
  * cancel rate  - cancelled flights / scheduled flights
  * trailing 12  - the 12 most recent months present in the data
"""

from __future__ import annotations

# --- Base views ------------------------------------------------------------
#
# Formatted once per source: `operations` over the marketing carrier table (flight,
# route and airport pages) and `operations_reporting` over the reporting carrier
# table (airline pages). Both canonical schemas share every column used here.
#
# `sched_dep_hour` interprets the reported hhmm string. Scheduled times are
# zero-padded and run 0001-2359 (verified 2026-09-26, DATA_NOTES.md); the `% 24`
# only guards against a 2400 turning up later.
BASE_VIEW = """
CREATE OR REPLACE VIEW {view} AS
SELECT
    *,
    (cancelled = 0 AND diverted = 0)                         AS operated,
    (cancelled = 1)                                          AS is_cancelled,
    (diverted = 1)                                           AS is_diverted,
    date_trunc('month', flight_date)                         AS flight_month,
    year(flight_date)                                        AS flight_year,
    month(flight_date)                                       AS month_of_year,
    isodow(flight_date)                                      AS day_of_week,
    CASE
        WHEN sched_dep IS NULL THEN NULL
        -- `//` is integer division: `/` would leave 1730 as 17.3.
        ELSE (TRY_CAST(sched_dep AS INTEGER) // 100) % 24
    END                                                      AS sched_dep_hour,
    coalesce(carrier_delay, 0) + coalesce(weather_delay, 0)
      + coalesce(nas_delay, 0) + coalesce(security_delay, 0)
      + coalesce(late_aircraft_delay, 0)                     AS attributed_delay_min
FROM read_parquet({parquet_glob!r}, union_by_name = true)
"""

# --- Shared metric expressions --------------------------------------------
# (column name, SQL expression). Applied identically to every grouping.
METRIC_EXPRESSIONS: tuple[tuple[str, str], ...] = (
    # Volume
    ("ops_scheduled", "count(*)"),
    ("ops_operated", "count(*) FILTER (WHERE operated)"),
    ("ops_cancelled", "count(*) FILTER (WHERE is_cancelled)"),
    ("ops_diverted", "count(*) FILTER (WHERE is_diverted)"),
    # Flights that operated AND carry a usable delay flag; this is the
    # denominator for on-time rate, so it is reported alongside it.
    ("ops_measurable", "count(*) FILTER (WHERE operated AND arr_del15 IS NOT NULL)"),
    # Headline rates. NULL rather than 0 when the denominator is empty, so a
    # missing value never reads as "0% on time".
    (
        "on_time_rate",
        "count(*) FILTER (WHERE operated AND arr_del15 = 0)::DOUBLE "
        "/ nullif(count(*) FILTER (WHERE operated AND arr_del15 IS NOT NULL), 0)",
    ),
    ("cancellation_rate", "count(*) FILTER (WHERE is_cancelled)::DOUBLE / nullif(count(*), 0)"),
    ("diversion_rate", "count(*) FILTER (WHERE is_diverted)::DOUBLE / nullif(count(*), 0)"),
    # Severity
    ("avg_arr_delay_min", "avg(arr_delay_min) FILTER (WHERE operated)"),
    ("avg_arr_delay_when_late_min", "avg(arr_delay_min) FILTER (WHERE operated AND arr_del15 = 1)"),
    (
        "median_arr_delay_when_late_min",
        "median(arr_delay_min) FILTER (WHERE operated AND arr_del15 = 1)",
    ),
    (
        "share_3h_plus",
        "count(*) FILTER (WHERE operated AND arr_delay_min >= 180)::DOUBLE "
        "/ nullif(count(*) FILTER (WHERE operated AND arr_delay_min IS NOT NULL), 0)",
    ),
    # Delay distribution buckets (counts; the export layer turns these into shares)
    ("bucket_on_time", "count(*) FILTER (WHERE operated AND arr_delay_min < 15)"),
    (
        "bucket_15_30",
        "count(*) FILTER (WHERE operated AND arr_delay_min >= 15 AND arr_delay_min < 30)",
    ),
    (
        "bucket_30_60",
        "count(*) FILTER (WHERE operated AND arr_delay_min >= 30 AND arr_delay_min < 60)",
    ),
    (
        "bucket_60_120",
        "count(*) FILTER (WHERE operated AND arr_delay_min >= 60 AND arr_delay_min < 120)",
    ),
    (
        "bucket_120_180",
        "count(*) FILTER (WHERE operated AND arr_delay_min >= 120 AND arr_delay_min < 180)",
    ),
    ("bucket_180_plus", "count(*) FILTER (WHERE operated AND arr_delay_min >= 180)"),
    ("bucket_cancelled_diverted", "count(*) FILTER (WHERE is_cancelled OR is_diverted)"),
    # Delay cause minutes. BTS populates these only for qualifying delays, so
    # shares are of attributed minutes, not of all delay minutes.
    ("carrier_delay_min", "sum(carrier_delay)"),
    ("weather_delay_min", "sum(weather_delay)"),
    ("nas_delay_min", "sum(nas_delay)"),
    ("security_delay_min", "sum(security_delay)"),
    ("late_aircraft_delay_min", "sum(late_aircraft_delay)"),
    ("attributed_delay_min", "sum(attributed_delay_min)"),
    # The scheduled departure a traveller would recognise. Flights are sometimes
    # retimed mid-year, so this is the most common value, not the only one.
    ("typical_sched_dep", "mode(sched_dep)"),
    # Coverage / freshness
    ("first_seen", "min(flight_date)"),
    ("last_seen", "max(flight_date)"),
    ("months_covered", "count(DISTINCT flight_month)"),
)

#: Grouped entity views: view name -> (key columns, source view).
#:
#: Airline figures come from the reporting carrier table and everything else from
#: the marketing carrier table (DECISIONS.md 2026-09-26), so `carrier` on a flight
#: is the brand on the ticket and `carrier` on an airline page is the reporting
#: carrier.
GROUPINGS: dict[str, tuple[tuple[str, ...], str]] = {
    "flight_metrics": (("carrier", "flight_number", "origin", "dest"), "operations_t12"),
    "route_metrics": (("origin", "dest"), "operations_t12"),
    "airline_metrics": (("carrier",), "operations_reporting_t12"),
}

#: Who flies each marketed flight. A flight can change operator (or operating
#: flight number) mid-year, so this names the most common pairing over the
#: trailing 12 months and the share of the schedule it flew. Ties break on the
#: codes themselves, so the choice is deterministic and exports stay reproducible.
FLIGHT_OPERATOR_VIEW = """
CREATE OR REPLACE VIEW flight_operator AS
WITH pairs AS (
    SELECT carrier, flight_number, origin, dest,
           operating_carrier, operating_flight_number, count(*) AS n
    FROM operations_t12
    GROUP BY ALL
),
ranked AS (
    SELECT *,
           sum(n) OVER (PARTITION BY carrier, flight_number, origin, dest) AS total,
           row_number() OVER (
               PARTITION BY carrier, flight_number, origin, dest
               ORDER BY n DESC, operating_carrier, operating_flight_number
           ) AS rank
    FROM pairs
)
SELECT carrier, flight_number, origin, dest,
       operating_carrier, operating_flight_number,
       n::DOUBLE / total AS operating_share
FROM ranked
WHERE rank = 1
"""

#: Seasonality and breakdown views.
#: view name -> (key columns, dimension columns, source view)
#:
#: Month-by-month series read the full history so a page can show a trend;
#: day-of-week, departure-hour and month-of-year breakdowns read the trailing 12
#: months, because mixing years would blend schedule changes into the pattern.
SEASONALITY: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    "flight_by_month": (
        ("carrier", "flight_number", "origin", "dest"),
        ("flight_month",),
        "operations",
    ),
    "route_by_month": (("origin", "dest"), ("flight_month",), "operations"),
    "airline_by_month": (("carrier",), ("flight_month",), "operations_reporting"),
    "airport_by_month": (("airport", "role"), ("flight_month",), "airport_operations"),
    "route_by_dow": (("origin", "dest"), ("day_of_week",), "operations_t12"),
    "route_by_dep_hour": (("origin", "dest"), ("sched_dep_hour",), "operations_t12"),
    "route_by_month_of_year": (("origin", "dest"), ("month_of_year",), "operations_t12"),
    "airport_by_dep_hour": (
        ("airport", "role"),
        ("sched_dep_hour",),
        "airport_operations_t12",
    ),
}


def metric_select(extra_indent: str = "    ") -> str:
    """The shared metric expression list, as a SQL SELECT fragment."""
    return (",\n" + extra_indent).join(f"{expr} AS {name}" for name, expr in METRIC_EXPRESSIONS)


def metric_names() -> tuple[str, ...]:
    return tuple(name for name, _ in METRIC_EXPRESSIONS)
