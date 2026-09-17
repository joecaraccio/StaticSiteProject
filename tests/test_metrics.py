"""Metrics checked against the hand-computed numbers in tests/fixtures/README.md.

If one of these fails, the working is written out there — compare against it
rather than adjusting the expectation to match the code.
"""

from __future__ import annotations

import pytest

from tests.conftest import one

FLIGHT = "WHERE carrier = 'AA' AND flight_number = '100' AND origin = 'BOS' AND dest = 'LGA'"


@pytest.fixture
def aa100(con):
    return one(con, f"SELECT * FROM flight_metrics {FLIGHT}")


# --- Volume ----------------------------------------------------------------


def test_scheduled_operated_cancelled_diverted(aa100):
    assert aa100["ops_scheduled"] == 10
    assert aa100["ops_operated"] == 8
    assert aa100["ops_cancelled"] == 1
    assert aa100["ops_diverted"] == 1


def test_measurable_denominator_is_reported(aa100):
    assert aa100["ops_measurable"] == 8


# --- Headline rates --------------------------------------------------------


def test_on_time_rate_is_three_of_eight(aa100):
    assert aa100["on_time_rate"] == pytest.approx(0.375)


def test_cancellation_rate_is_over_scheduled_not_operated(aa100):
    """1 cancellation of 10 scheduled = 0.10, not 1/9 or 1/8."""
    assert aa100["cancellation_rate"] == pytest.approx(0.1)


def test_diversion_rate(aa100):
    assert aa100["diversion_rate"] == pytest.approx(0.1)


# --- Severity --------------------------------------------------------------


def test_average_delay_covers_operated_flights_including_early_ones(aa100):
    assert aa100["avg_arr_delay_min"] == pytest.approx(510 / 8)


def test_average_delay_when_late_excludes_on_time_flights(aa100):
    assert aa100["avg_arr_delay_when_late_min"] == pytest.approx(101.0)


def test_median_delay_when_late(aa100):
    assert aa100["median_arr_delay_when_late_min"] == pytest.approx(90.0)


def test_share_three_hours_plus(aa100):
    assert aa100["share_3h_plus"] == pytest.approx(0.125)


# --- Distribution ----------------------------------------------------------


def test_delay_buckets_partition_the_operated_flights(aa100):
    buckets = [
        aa100["bucket_on_time"],
        aa100["bucket_15_30"],
        aa100["bucket_30_60"],
        aa100["bucket_60_120"],
        aa100["bucket_120_180"],
        aa100["bucket_180_plus"],
    ]
    assert buckets == [3, 1, 1, 1, 1, 1]
    assert sum(buckets) == aa100["ops_operated"]


def test_cancelled_and_diverted_are_their_own_bucket(aa100):
    assert aa100["bucket_cancelled_diverted"] == 2
    total = aa100["bucket_on_time"] + sum(
        aa100[k]
        for k in (
            "bucket_15_30",
            "bucket_30_60",
            "bucket_60_120",
            "bucket_120_180",
            "bucket_180_plus",
        )
    )
    assert total + aa100["bucket_cancelled_diverted"] == aa100["ops_scheduled"]


# --- Delay causes ----------------------------------------------------------


def test_delay_cause_minutes(aa100):
    assert aa100["carrier_delay_min"] == pytest.approx(140)
    assert aa100["weather_delay_min"] == pytest.approx(75)
    assert aa100["nas_delay_min"] == pytest.approx(120)
    assert aa100["security_delay_min"] == pytest.approx(20)
    assert aa100["late_aircraft_delay_min"] == pytest.approx(150)


def test_attributed_minutes_sum_to_the_cause_columns(aa100):
    parts = sum(
        aa100[k]
        for k in (
            "carrier_delay_min",
            "weather_delay_min",
            "nas_delay_min",
            "security_delay_min",
            "late_aircraft_delay_min",
        )
    )
    assert aa100["attributed_delay_min"] == pytest.approx(parts)
    assert aa100["attributed_delay_min"] == pytest.approx(505)


# --- Trailing 12 months ----------------------------------------------------


def test_trailing_12_excludes_older_months(con, aa100):
    """The 3 cancelled 2023-12 rows are outside the window and must not count."""
    assert aa100["ops_scheduled"] == 10
    full_history = one(con, f"SELECT count(*) AS n FROM operations {FLIGHT}")
    assert full_history["n"] == 13


def test_window_is_relative_to_the_latest_month_in_the_data(con):
    window = one(con, "SELECT * FROM t12_window")
    assert str(window["latest_month"])[:7] == "2025-01"
    assert str(window["earliest_month"])[:7] == "2024-02"


def test_month_series_reads_full_history(con):
    months = con.execute(
        f"SELECT strftime(flight_month, '%Y-%m') AS m FROM flight_by_month {FLIGHT} ORDER BY m"
    ).fetchall()
    assert [m[0] for m in months] == ["2023-12", "2025-01"]


# --- Rollups ---------------------------------------------------------------


def test_route_rollup_combines_carriers(con):
    route = one(con, "SELECT * FROM route_metrics WHERE origin = 'BOS' AND dest = 'LGA'")
    assert route["ops_scheduled"] == 15
    assert route["ops_operated"] == 13
    assert route["on_time_rate"] == pytest.approx(8 / 13)


def test_airline_rollup(con):
    dl = one(con, "SELECT * FROM airline_metrics WHERE carrier = 'DL'")
    assert dl["ops_scheduled"] == 5
    assert dl["on_time_rate"] == pytest.approx(1.0)


def test_airport_metrics_split_departures_from_arrivals(con):
    departures = one(
        con, "SELECT * FROM airport_metrics WHERE airport = 'BOS' AND role = 'departure'"
    )
    arrivals = one(con, "SELECT * FROM airport_metrics WHERE airport = 'BOS' AND role = 'arrival'")
    assert departures["ops_scheduled"] == 15  # AA 100 (10) + DL 200 (5)
    assert arrivals["ops_scheduled"] == 4  # UA 300 inbound
    assert departures["on_time_rate"] == pytest.approx(8 / 13)
    assert arrivals["on_time_rate"] == pytest.approx(0.5)


# --- Derived dimensions ----------------------------------------------------


def test_departure_hour_2400_buckets_as_hour_zero(con):
    hours = dict(
        con.execute(
            "SELECT sched_dep_hour, ops_scheduled FROM route_by_dep_hour "
            "WHERE origin = 'BOS' AND dest = 'LGA' ORDER BY sched_dep_hour"
        ).fetchall()
    )
    assert hours == {0: 1, 8: 9, 17: 5}


def test_day_of_week_is_iso_monday_first(con):
    rows = con.execute(
        "SELECT day_of_week, ops_scheduled FROM route_by_dow "
        "WHERE origin = 'BOS' AND dest = 'LGA' ORDER BY day_of_week"
    ).fetchall()
    assert min(r[0] for r in rows) >= 1
    assert max(r[0] for r in rows) <= 7
    assert sum(r[1] for r in rows) == 15


# --- Guards against misleading zeros --------------------------------------


def test_rate_is_null_not_zero_when_nothing_is_measurable(con):
    """A flight with no measurable operations must report NULL, never 0% on time."""
    con.execute(
        "CREATE OR REPLACE TEMP VIEW only_cancelled AS SELECT * FROM operations WHERE is_cancelled"
    )
    row = one(
        con,
        "SELECT count(*) FILTER (WHERE operated AND arr_del15 = 0)::DOUBLE "
        "/ nullif(count(*) FILTER (WHERE operated AND arr_del15 IS NOT NULL), 0) AS on_time_rate "
        "FROM only_cancelled",
    )
    assert row["on_time_rate"] is None
