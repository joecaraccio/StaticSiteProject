"""The two BTS tables disagree on purpose, and each page type reads the right one.

DECISIONS.md 2026-09-26: flight, route and airport pages read the marketing
carrier table, which includes regional operators that do not report to BTS;
airline pages read the reporting carrier table. These rows are synthetic and
built so the two tables differ in exactly the ways the real ones do.

Marketing table, BOS -> LGA, 2025-01:
  DL 3860  x4  operated by 9E 5538 three times, by OO 5000 once   (all on time)
  DL 200   x2  operated by DL 200                                  (one 30 min late)
  DL 77    x2  operated by 9E 77 once and OO 77 once               (a tie)

Reporting table, same month: only carriers that report, under their own codes.
  DL 200   x2  (the same two flights)
  OO 5000  x1  (the one DL 3860 that OO flew)
  OO 77    x1
9E does not report, so its four flights exist only in the marketing table.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import duckdb
import pytest

from pipeline import config, normalize
from pipeline.export import pages
from pipeline.metrics import build
from pipeline.sources import bts_ontime

from .conftest import one, stage_zip

MONTH = "2025-01"

SHARED = {
    "Origin": "BOS",
    "OriginAirportID": "90001",
    "Dest": "LGA",
    "DestAirportID": "90002",
    "CRSDepTime": "0800",
    "DepTime": "0800",
    "CRSArrTime": "0925",
    "ArrTime": "0925",
    "DepDelayMinutes": "0.00",
    "ArrDelayMinutes": "0.00",
    "ArrDel15": "0.00",
    "Cancelled": "0.00",
    "CancellationCode": "",
    "Diverted": "0.00",
    "CarrierDelay": "",
    "WeatherDelay": "",
    "NASDelay": "",
    "SecurityDelay": "",
    "LateAircraftDelay": "",
    "Distance": "185.00",
}
LATE = {
    "ArrTime": "0955",
    "ArrDelayMinutes": "30.00",
    "ArrDel15": "1.00",
    "CarrierDelay": "30.00",
    "WeatherDelay": "0.00",
    "NASDelay": "0.00",
    "SecurityDelay": "0.00",
    "LateAircraftDelay": "0.00",
}
DOT_ID = {"DL": "90020", "9E": "90040", "OO": "90050"}


def marketing(day: int, brand: str, number: str, operator: str, op_number: str, **extra):
    return {
        "FlightDate": f"2025-01-{day:02d}",
        "Marketing_Airline_Network": brand,
        "DOT_ID_Marketing_Airline": DOT_ID[brand],
        "Flight_Number_Marketing_Airline": number,
        "Operating_Airline ": operator,  # trailing space, as BTS ships it
        "DOT_ID_Operating_Airline": DOT_ID[operator],
        "Flight_Number_Operating_Airline": op_number,
        **SHARED,
        **extra,
    }


def reporting(day: int, carrier: str, number: str, **extra):
    return {
        "FlightDate": f"2025-01-{day:02d}",
        "Reporting_Airline": carrier,
        "DOT_ID_Reporting_Airline": DOT_ID[carrier],
        "Flight_Number_Reporting_Airline": number,
        **SHARED,
        **extra,
    }


MARKETING_ROWS = [
    marketing(6, "DL", "3860", "9E", "5538"),
    marketing(7, "DL", "3860", "9E", "5538"),
    marketing(8, "DL", "3860", "9E", "5538"),
    marketing(9, "DL", "3860", "OO", "5000"),
    marketing(6, "DL", "200", "DL", "200"),
    marketing(7, "DL", "200", "DL", "200", **LATE),
    marketing(6, "DL", "77", "OO", "77"),
    marketing(7, "DL", "77", "9E", "77"),
]
REPORTING_ROWS = [
    reporting(6, "DL", "200"),
    reporting(7, "DL", "200", **LATE),
    reporting(9, "OO", "5000"),
    reporting(6, "OO", "77"),
]


@pytest.fixture
def split(data_root) -> duckdb.DuckDBPyConnection:
    stage_zip(bts_ontime.MARKETING, MONTH, MARKETING_ROWS)
    stage_zip(bts_ontime.REPORTING, MONTH, REPORTING_ROWS)
    year, month = bts_ontime.parse_month(MONTH)
    for source in bts_ontime.SOURCES:
        normalize.normalize_month(source, year, month)
    connection = duckdb.connect()
    build.build_views(connection)
    yield connection
    connection.close()


def test_route_counts_flights_by_non_reporting_operators(split):
    """All eight marketed flights count, including the five flown by 9E and OO."""
    route = one(split, "SELECT * FROM route_metrics WHERE origin = 'BOS' AND dest = 'LGA'")
    assert route["ops_scheduled"] == 8


def test_airport_counts_every_flight_too(split):
    bos = one(split, "SELECT * FROM airport_metrics WHERE airport = 'BOS' AND role = 'departure'")
    assert bos["ops_scheduled"] == 8


def test_airline_figures_come_from_the_reporting_table(split):
    rows = dict(split.execute("SELECT carrier, ops_scheduled FROM airline_metrics").fetchall())
    # DL's own record is its two flights, not the eight sold under its brand;
    # 9E never reported, so it has no airline page at all.
    assert rows == {"DL": 2, "OO": 2}


def test_flights_are_keyed_by_the_number_on_the_ticket(split):
    keys = split.execute(
        "SELECT carrier, flight_number, ops_scheduled FROM flight_metrics ORDER BY ALL"
    ).fetchall()
    assert keys == [("DL", "200", 2), ("DL", "3860", 4), ("DL", "77", 2)]


def test_operator_is_the_most_common_one(split):
    op = one(split, "SELECT * FROM flight_operator WHERE flight_number = '3860'")
    assert (op["operating_carrier"], op["operating_flight_number"]) == ("9E", "5538")
    assert op["operating_share"] == pytest.approx(0.75)


def test_operator_ties_break_deterministically(split):
    """One flight each by 9E and OO: the lower code wins, every time."""
    op = one(split, "SELECT * FROM flight_operator WHERE flight_number = '77'")
    assert op["operating_carrier"] == "9E"
    assert op["operating_share"] == pytest.approx(0.5)


def test_flight_page_names_its_operator(split):
    # Four flights is below the flight page gate, so build the document directly
    # rather than through export_all, which would drop it.
    keys = {"carrier": "DL", "flight_number": "3860", "origin": "BOS", "dest": "LGA"}
    row = one(split, "SELECT * FROM flight_metrics WHERE flight_number = '3860'")
    operated_by = pages._operators(split)[tuple(keys.values())]
    alternatives = pages._alternatives(split, "flight", keys)
    doc = pages._build_document(
        "flight",
        row,
        keys,
        "/flights/DL/3860/BOS-LGA",
        [],
        alternatives,
        (date(2025, 1, 1), date(2025, 1, 31)),
        datetime(2025, 2, 1, tzinfo=UTC),
        operated_by,
    )
    assert doc["operated_by"] == {"carrier": "9E", "flight_number": "5538", "share": 0.75}
    assert doc["source"]["table"] == bts_ontime.MARKETING.title
    alts = {a["flight_number"]: a["operating_carrier"] for a in doc["alternatives"]}
    assert alts == {"3860": "9E", "200": "DL", "77": "9E"}


def test_airline_page_cites_the_reporting_table(split):
    pages.export_all(con=split, today=date(2025, 2, 15))
    doc = json.loads((config.PATHS.export / "pages" / "airlines" / "DL.json").read_text())
    assert doc["source"]["table"] == bts_ontime.REPORTING.title
    assert doc["operated_by"] is None
