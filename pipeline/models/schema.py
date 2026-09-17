"""Canonical schema for the `operations` table, and the *candidate* mapping onto
BTS source columns.

Why "candidate": CLAUDE.md requires download URLs, file formats and column names
to be confirmed against the live source before code depends on them. The names
below come from prior familiarity with the BTS On-Time Performance table and are
NOT confirmed. `pipeline.sources.verify` checks them against the real CSV header
and records the result; `ingest` refuses to run until that record exists.

So this module is a hypothesis the verifier proves, not a statement of fact.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    """One canonical column.

    name:        canonical name used everywhere downstream
    source:      candidate BTS column name (verified at ingest time)
    sql_type:    DuckDB type the normalizer casts to
    required:    normalization fails if the column is missing from the source
    note:        anything a reader needs to know about the semantics
    """

    name: str
    source: str
    sql_type: str
    required: bool = True
    note: str = ""


# Ordered: this is also the column order of data/clean/operations/*.parquet.
OPERATIONS_FIELDS: tuple[Field, ...] = (
    Field("flight_date", "FlightDate", "DATE", note="Local date of scheduled departure"),
    Field("carrier", "Reporting_Airline", "VARCHAR", note="Reporting (operating) carrier code"),
    Field(
        "carrier_id",
        "DOT_ID_Reporting_Airline",
        "INTEGER",
        note="BTS unique carrier ID; stable across code reuse",
    ),
    Field("flight_number", "Flight_Number_Reporting_Airline", "VARCHAR"),
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

# Lineage columns the normalizer adds; they have no source column.
LINEAGE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("source_file", "VARCHAR"),
    ("ingested_at", "TIMESTAMP"),
)


def source_columns(required_only: bool = False) -> tuple[str, ...]:
    return tuple(f.source for f in OPERATIONS_FIELDS if f.required or not required_only)


def by_source_name() -> dict[str, Field]:
    return {f.source: f for f in OPERATIONS_FIELDS}


def canonical_columns() -> tuple[str, ...]:
    return tuple(f.name for f in OPERATIONS_FIELDS) + tuple(n for n, _ in LINEAGE_COLUMNS)
