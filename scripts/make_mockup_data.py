#!/usr/bin/env python
"""Generate a synthetic dataset for design work, and build the site from it.

WHY THIS EXISTS, AND WHAT IT IS NOT
-----------------------------------
CLAUDE.md forbids inventing data. That rule is about what reaches a *published
page*: no placeholder statistics presented as real, no fixtures pretending to be
BTS output. A mockup still needs numbers to have a shape to judge, so this script
makes the synthetic nature impossible to miss or to ship:

* it writes to its own data root (`data/mockup/`) and refuses to touch the real one;
* every figure it produces flows into pages stamped with a `demo_notice`, which
  the site renders as a persistent banner and which forces `noindex`;
* the generated site builds to `site/dist-mockup/`, never `site/dist/`.

Airport and carrier codes are real because they are public facts, not statistics.
Every *number* here is invented, and every page says so.

The data is generated in the BTS source column layout and pushed through the real
normalize -> build -> export path, so what you are looking at is the actual
pipeline output, not a hand-drawn approximation of it.

Usage:
    uv run python scripts/make_mockup_data.py
    uv run python scripts/make_mockup_data.py --months 24 --seed 7
"""

from __future__ import annotations

import argparse
import csv
import random
import subprocess
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MOCKUP_ROOT = REPO / "data" / "mockup"

DEMO_NOTICE = (
    "Mockup: every figure on this page is synthetic, generated for design review. "
    "It is not U.S. DOT data and must not be read as a description of any real flight."
)

# Real codes (public facts). Only the numbers below are invented.
HUBS = ["ORD", "ATL"]
SPOKES = ["BOS", "LGA", "DEN", "SFO"]
CARRIERS = {
    "AA": (19805, "American"),
    "DL": (19790, "Delta"),
    "UA": (19977, "United"),
    "WN": (19393, "Southwest"),
    "B6": (20409, "JetBlue"),
}
AIRPORT_IDS = {"ORD": 13930, "ATL": 10397, "BOS": 10721, "LGA": 12953, "DEN": 11292, "SFO": 14771}
DISTANCE = {
    frozenset(("ORD", "ATL")): 606,
    frozenset(("ORD", "BOS")): 867,
    frozenset(("ORD", "LGA")): 733,
    frozenset(("ORD", "DEN")): 888,
    frozenset(("ORD", "SFO")): 1846,
    frozenset(("ATL", "BOS")): 946,
    frozenset(("ATL", "LGA")): 762,
    frozenset(("ATL", "DEN")): 1199,
    frozenset(("ATL", "SFO")): 2139,
}

COLUMNS = [
    "FlightDate",
    "Reporting_Airline",
    "DOT_ID_Reporting_Airline",
    "Flight_Number_Reporting_Airline",
    "Origin",
    "OriginAirportID",
    "Dest",
    "DestAirportID",
    "CRSDepTime",
    "DepTime",
    "CRSArrTime",
    "ArrTime",
    "DepDelayMinutes",
    "ArrDelayMinutes",
    "ArrDel15",
    "Cancelled",
    "CancellationCode",
    "Diverted",
    "CarrierDelay",
    "WeatherDelay",
    "NASDelay",
    "SecurityDelay",
    "LateAircraftDelay",
    "Distance",
]

# Month-of-year multipliers on the delay rate: summer thunderstorms and winter
# weather, both invented but shaped so seasonality charts have something to show.
SEASONALITY = {
    1: 1.35,
    2: 1.25,
    3: 1.05,
    4: 0.95,
    5: 0.95,
    6: 1.30,
    7: 1.40,
    8: 1.25,
    9: 0.85,
    10: 0.80,
    11: 0.95,
    12: 1.45,
}


def month_starts(count: int, end: date) -> list[date]:
    """`count` month-start dates ending with the month containing `end`."""
    months = []
    year, month = end.year, end.month
    for _ in range(count):
        months.append(date(year, month, 1))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return sorted(months)


def build_schedule(rng: random.Random) -> list[dict]:
    """Invent a flight schedule: who flies what, when, and how good they are at it."""
    directed = []
    for hub in HUBS:
        for spoke in SPOKES:
            directed += [(hub, spoke), (spoke, hub)]
    directed += [("ORD", "ATL"), ("ATL", "ORD")]

    schedule = []
    for origin, dest in directed:
        carriers = rng.sample(list(CARRIERS), k=rng.choice([2, 3]))
        departures = rng.sample([6, 7, 8, 10, 12, 14, 16, 17, 19, 21], k=4)
        for i, hour in enumerate(sorted(departures)):
            carrier = carriers[i % len(carriers)]
            schedule.append(
                {
                    "carrier": carrier,
                    "flight_number": str(rng.randint(100, 2999)),
                    "origin": origin,
                    "dest": dest,
                    "dep_hour": hour,
                    "dep_minute": rng.choice([0, 5, 15, 20, 30, 40, 45, 50]),
                    # Later departures absorb the day's accumulated delay, which is a
                    # real pattern worth having the mockup show.
                    "base_delay_rate": min(
                        0.55, 0.10 + (hour - 6) * 0.022 + rng.uniform(-0.03, 0.05)
                    ),
                    "cancel_rate": rng.uniform(0.004, 0.030),
                    "block_minutes": 70 + int(DISTANCE[frozenset((origin, dest))] * 0.11),
                    "days": sorted(rng.sample(range(7), k=rng.choice([5, 6, 7, 7]))),
                }
            )
    return schedule


def generate_rows(months: int, seed: int) -> tuple[list[dict], date, date]:
    rng = random.Random(seed)
    schedule = build_schedule(rng)

    # End a couple of months back, mirroring BTS's real publishing lag.
    today = date.today()
    end_month = date(today.year, today.month, 1) - timedelta(days=1)
    end_month = date(end_month.year, end_month.month, 1) - timedelta(days=1)
    starts = month_starts(months, end_month)

    rows: list[dict] = []
    for month_start in starts:
        next_month = (
            date(month_start.year + 1, 1, 1)
            if month_start.month == 12
            else date(month_start.year, month_start.month + 1, 1)
        )
        season = SEASONALITY[month_start.month]
        day = month_start
        while day < next_month:
            for flight in schedule:
                if day.weekday() not in flight["days"]:
                    continue
                rows.append(_operate(flight, day, season, rng))
            day += timedelta(days=1)

    return rows, starts[0], max(starts[-1], rows[-1]["_date"])


def _hhmm(hour: int, minute: int) -> str:
    return f"{hour % 24:02d}{minute:02d}"


def _operate(flight: dict, day: date, season: float, rng: random.Random) -> dict:
    """One scheduled flight on one day. Every value here is invented."""
    origin, dest = flight["origin"], flight["dest"]
    sched_dep = _hhmm(flight["dep_hour"], flight["dep_minute"])
    arr_total = flight["dep_hour"] * 60 + flight["dep_minute"] + flight["block_minutes"]
    sched_arr = _hhmm((arr_total // 60) % 24, arr_total % 60)

    base = dict.fromkeys(COLUMNS, "")
    base.update(
        {
            "FlightDate": day.isoformat(),
            "Reporting_Airline": flight["carrier"],
            "DOT_ID_Reporting_Airline": str(CARRIERS[flight["carrier"]][0]),
            "Flight_Number_Reporting_Airline": flight["flight_number"],
            "Origin": origin,
            "OriginAirportID": str(AIRPORT_IDS[origin]),
            "Dest": dest,
            "DestAirportID": str(AIRPORT_IDS[dest]),
            "CRSDepTime": sched_dep,
            "CRSArrTime": sched_arr,
            "Cancelled": "0.00",
            "Diverted": "0.00",
            "Distance": f"{DISTANCE[frozenset((origin, dest))]}.00",
        }
    )

    if rng.random() < flight["cancel_rate"] * season:
        base["Cancelled"] = "1.00"
        base["CancellationCode"] = rng.choices(["A", "B", "C"], weights=[3, 5, 2])[0]
        return {**base, "_date": day}

    if rng.random() < 0.002:
        base["Diverted"] = "1.00"
        base["DepTime"] = sched_dep
        return {**base, "_date": day}

    late = rng.random() < flight["base_delay_rate"] * season
    if not late:
        arr_delay = rng.randint(-22, 14)
    else:
        # A long tail: most delays are short, a few are very long.
        arr_delay = int(rng.lognormvariate(3.5, 0.75)) + 15
        arr_delay = min(arr_delay, 420)

    dep_delay = max(0, arr_delay - rng.randint(-8, 12))
    actual_arr_total = arr_total + arr_delay
    base["DepTime"] = _hhmm(
        ((flight["dep_hour"] * 60 + flight["dep_minute"] + dep_delay) // 60) % 24,
        (flight["dep_minute"] + dep_delay) % 60,
    )
    base["ArrTime"] = _hhmm((actual_arr_total // 60) % 24, actual_arr_total % 60)
    base["DepDelayMinutes"] = f"{dep_delay}.00"
    base["ArrDelayMinutes"] = f"{max(0, arr_delay)}.00"
    base["ArrDel15"] = "1.00" if arr_delay >= 15 else "0.00"

    # BTS only populates cause columns for qualifying delays, so the mockup does too.
    if arr_delay >= 15:
        weights = [0.30, 0.12, 0.25, 0.01, 0.32]
        if SEASONALITY[day.month] > 1.2:
            weights = [0.22, 0.30, 0.23, 0.01, 0.24]
        split = [w / sum(weights) for w in weights]
        remaining = arr_delay
        keys = ["CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay"]
        for i, key in enumerate(keys[:-1]):
            minutes = int(arr_delay * split[i] * rng.uniform(0.4, 1.6))
            minutes = min(minutes, remaining)
            base[key] = f"{minutes}.00"
            remaining -= minutes
        base[keys[-1]] = f"{remaining}.00"

    return {**base, "_date": day}


def write_zip(rows: list[dict], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    csv_path = destination.with_suffix(".csv")
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(csv_path, arcname="SYNTHETIC_MOCKUP_DATA_NOT_BTS.csv")
    csv_path.unlink()


def run(args: list[str], data_root: Path) -> None:
    import os

    env = {**os.environ, "DATA_ROOT": str(data_root)}
    print(f"  $ pipeline {' '.join(args)}")
    result = subprocess.run(
        [sys.executable, "-m", "pipeline", *args],
        env=env,
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    print("    " + (result.stdout or result.stderr).strip().replace("\n", "\n    "))
    if result.returncode != 0:
        raise SystemExit(f"pipeline {args[0]} failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--months", type=int, default=24, help="months of history to invent")
    parser.add_argument(
        "--seed", type=int, default=20260917, help="RNG seed; the run is deterministic"
    )
    parser.add_argument("--keep", action="store_true", help="reuse existing generated data")
    parser.add_argument(
        "--generated-at",
        default="2026-09-17",
        metavar="YYYY-MM-DD",
        help="pinned export timestamp; keeps the committed mockup diff-free",
    )
    args = parser.parse_args()

    # Safety rail: this must never write into the real data root.
    if MOCKUP_ROOT.resolve() == (REPO / "data").resolve():
        raise SystemExit("Refusing to run: the mockup root must not be the real data root.")

    if not args.keep:
        print(f"Generating {args.months} months of synthetic operations (seed {args.seed})...")
        rows, first, last = generate_rows(args.months, args.seed)
        print(f"  {len(rows):,} rows, {first} to {last}")
        month_label = f"{last.year:04d}-{last.month:02d}"
        write_zip(
            rows,
            MOCKUP_ROOT
            / "raw"
            / "bts_ontime_reporting_carrier"
            / f"{last.year:04d}"
            / f"bts_ontime_reporting_carrier_{month_label}.zip",
        )
        run(["normalize", "--months", month_label], MOCKUP_ROOT)

    run(["build"], MOCKUP_ROOT)
    # The export is committed to git, so its timestamp is pinned: re-running this
    # script produces no diff unless the pipeline's actual output changed, which
    # turns data/mockup/export into a snapshot test of the whole chain.
    run(
        [
            "export",
            "--demo-notice",
            DEMO_NOTICE,
            "--generated-at",
            f"{args.generated_at}T00:00:00+00:00",
        ],
        MOCKUP_ROOT,
    )

    print()
    print("Mockup data ready. Build the site against it with:")
    print(f"  cd site && PAGES_DIR={MOCKUP_ROOT}/export OUT_DIR=dist-mockup npm run build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
