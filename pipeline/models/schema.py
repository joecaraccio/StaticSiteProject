"""Canonical schemas for the two BTS on-time tables, and their mapping onto source
columns.

Both tables describe the same kind of event, one row per scheduled flight, and
share every column except flight identity:

* the **reporting carrier** table names the airline that filed the record
  (`Reporting_Airline`) — BTS's official carrier record, used for airline pages;
* the **marketing carrier** table names the brand the flight was sold under
  (`Marketing_Airline_Network`) and carries the operator alongside it — the
  source for flight, route and airport pages. See DECISIONS.md 2026-09-26.

So both canonical schemas have `carrier` and `flight_number`, meaning the
reporting carrier in one and the marketing carrier in the other, and the
marketing schema adds the operating carrier. The metric SQL runs unchanged over
either.

Every mapping here was checked against the live source by
`pipeline.sources.verify` (2026-09-26, month 2025-01). Editing a mapping changes
its fingerprint and forces a re-check before `ingest` will run again.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    """One canonical column.

    name:        canonical name used everywhere downstream
    source:      BTS column name (verified at ingest time)
    sql_type:    DuckDB type the normalizer casts to
    required:    normalization fails if the column is missing from the source
    note:        anything a reader needs to know about the semantics
    """

    name: str
    source: str
    sql_type: str
    required: bool = True
    note: str = ""


# Everything after flight identity. Identical names in both tables.
_SHARED_FIELDS: tuple[Field, ...] = (
    Field("origin", "Origin", "VARCHAR"),
    Field("origin_airport_id", "OriginAirportID", "INTEGER"),
    Field("dest", "Dest", "VARCHAR"),
    Field("dest_airport_id", "DestAirportID", "INTEGER"),
    Field("sched_dep", "CRSDepTime", "VARCHAR", note="Local hhmm as reported; 2400 is possible"),
    Field("actual_dep", "DepTime", "VARCHAR", required=False, note="Null when cancelled"),
    Field("sched_arr", "CRSArrTime", "VARCHAR", note="Local hhmm as reported"),
    Field("actual_arr", "ArrTime", "VARCHAR", required=False, note="Null when cancelled/diverted"),
    Field(
        "dep_delay_min",
        "DepDelayMinutes",
        "DOUBLE",
        required=False,
        note="Early counts as 0, not negative",
    ),
    Field("arr_delay_min", "ArrDelayMinutes", "DOUBLE", required=False),
    Field("arr_del15", "ArrDel15", "DOUBLE", required=False, note="1.0 when >=15 min late"),
    Field("cancelled", "Cancelled", "DOUBLE", note="1.0 when cancelled"),
    Field("cancellation_code", "CancellationCode", "VARCHAR", required=False),
    Field("diverted", "Diverted", "DOUBLE"),
    Field(
        "carrier_delay",
        "CarrierDelay",
        "DOUBLE",
        required=False,
        note="Only populated for qualifying delays",
    ),
    Field("weather_delay", "WeatherDelay", "DOUBLE", required=False),
    Field("nas_delay", "NASDelay", "DOUBLE", required=False),
    Field("security_delay", "SecurityDelay", "DOUBLE", required=False),
    Field("late_aircraft_delay", "LateAircraftDelay", "DOUBLE", required=False),
    Field("distance", "Distance", "DOUBLE", required=False),
)

# Ordered: this is also the column order of the source's Parquet files.
REPORTING_FIELDS: tuple[Field, ...] = (
    Field("flight_date", "FlightDate", "DATE", note="Local date of scheduled departure"),
    Field("carrier", "Reporting_Airline", "VARCHAR", note="Reporting (operating) carrier code"),
    Field(
        "carrier_id",
        "DOT_ID_Reporting_Airline",
        "INTEGER",
        note="BTS unique carrier ID; stable across code reuse",
    ),
    Field("flight_number", "Flight_Number_Reporting_Airline", "VARCHAR"),
    *_SHARED_FIELDS,
)

MARKETING_FIELDS: tuple[Field, ...] = (
    Field("flight_date", "FlightDate", "DATE", note="Local date of scheduled departure"),
    Field(
        "carrier",
        "Marketing_Airline_Network",
        "VARCHAR",
        note="Marketing carrier: the brand on the ticket",
    ),
    Field("carrier_id", "DOT_ID_Marketing_Airline", "INTEGER", note="BTS unique carrier ID"),
    Field(
        "flight_number",
        "Flight_Number_Marketing_Airline",
        "VARCHAR",
        note="The number on the ticket",
    ),
    Field(
        "operating_carrier",
        # BTS's header is "Operating_Airline " with a trailing space; headers are
        # matched after trimming (see normalize and verify).
        "Operating_Airline",
        "VARCHAR",
        note="Who flies it; may not report to BTS itself",
    ),
    Field("operating_carrier_id", "DOT_ID_Operating_Airline", "INTEGER"),
    Field(
        "operating_flight_number",
        "Flight_Number_Operating_Airline",
        "VARCHAR",
        note="Can differ from the marketing number",
    ),
    *_SHARED_FIELDS,
)

# Lineage columns the normalizer adds; they have no source column.
LINEAGE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("source_file", "VARCHAR"),
    ("ingested_at", "TIMESTAMP"),
)


def by_source_name(fields: tuple[Field, ...]) -> dict[str, Field]:
    return {f.source: f for f in fields}


def canonical_columns(fields: tuple[Field, ...]) -> tuple[str, ...]:
    return tuple(f.name for f in fields) + tuple(n for n, _ in LINEAGE_COLUMNS)
