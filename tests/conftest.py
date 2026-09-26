"""Shared fixtures.

Every test runs against a throwaway DATA_ROOT so nothing touches a real
`data/` directory, and the synthetic sample is pushed through the *real* code
path — zipped, normalized, then queried — rather than loaded directly.

The fixture CSV is shaped like the reporting carrier table. Its marketing carrier
twin is derived here by renaming the identity columns, with every flight marketed
and operated by the same carrier, so both tables hold the same 22 flights and the
hand-computed reference numbers hold for either. Tests about the two tables
*differing* stage their own rows with `stage_zip`.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import duckdb
import pytest

from pipeline import config, normalize
from pipeline.metrics import build
from pipeline.sources import bts_ontime

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "synthetic_ontime_sample.csv"

#: The fixture's months, and the month the reference numbers are computed for.
FIXTURE_MONTHS = ("2023-12", "2025-01")
REFERENCE_MONTH = "2025-01"

#: Reporting column -> marketing column, for the identity columns that differ.
#: `Operating_Airline ` keeps the trailing space BTS really ships (DATA_NOTES.md).
MARKETING_RENAMES = {
    "Reporting_Airline": "Marketing_Airline_Network",
    "DOT_ID_Reporting_Airline": "DOT_ID_Marketing_Airline",
    "Flight_Number_Reporting_Airline": "Flight_Number_Marketing_Airline",
}
OPERATING_COPIES = {
    "Operating_Airline ": "Reporting_Airline",
    "DOT_ID_Operating_Airline": "DOT_ID_Reporting_Airline",
    "Flight_Number_Operating_Airline": "Flight_Number_Reporting_Airline",
}


def marketing_twin(reporting_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """The same flights as marketing-table rows, each operated by its own brand."""
    twin = []
    for row in reporting_rows:
        out = {MARKETING_RENAMES.get(k, k): v for k, v in row.items()}
        out.update({new: row[old] for new, old in OPERATING_COPIES.items()})
        twin.append(out)
    return twin


def read_fixture() -> list[dict[str, str]]:
    with FIXTURE_CSV.open(newline="") as fh:
        return list(csv.DictReader(fh))


def stage_zip(source: bts_ontime.Source, month: str, rows: list[dict[str, str]]) -> Path:
    """Write rows as a raw monthly zip for `source`, where ingest would put it."""
    year, month_num = bts_ontime.parse_month(month)
    target = bts_ontime.raw_path(source, year, month_num)
    target.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{source.id}_sample.csv", buffer.getvalue())
    return target


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> config.Paths:
    """Point the pipeline at an empty temporary data directory."""
    paths = config.Paths(root=tmp_path / "data")
    monkeypatch.setattr(config, "PATHS", paths)
    monkeypatch.setattr(config, "DOWNLOAD_DELAY_SECONDS", 0.0)
    paths.ensure()
    return paths


@pytest.fixture
def raw_fixture_zip(data_root: config.Paths) -> dict[str, Path]:
    """Stage the synthetic sample as a raw monthly zip for each source."""
    rows = read_fixture()
    return {
        bts_ontime.REPORTING.id: stage_zip(bts_ontime.REPORTING, REFERENCE_MONTH, rows),
        bts_ontime.MARKETING.id: stage_zip(
            bts_ontime.MARKETING, REFERENCE_MONTH, marketing_twin(rows)
        ),
    }


@pytest.fixture
def normalized(raw_fixture_zip: dict[str, Path]) -> dict[str, normalize.NormalizeResult]:
    year, month = bts_ontime.parse_month(REFERENCE_MONTH)
    return {s.id: normalize.normalize_month(s, year, month) for s in bts_ontime.SOURCES}


@pytest.fixture
def con(normalized: dict[str, normalize.NormalizeResult]) -> duckdb.DuckDBPyConnection:
    """An in-memory connection with every metric view built over the fixture."""
    connection = duckdb.connect()
    build.build_views(connection)
    yield connection
    connection.close()


def one(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> dict:
    """Run a query expected to return exactly one row; return it as a dict."""
    cursor = con.execute(sql, params or [])
    rows = cursor.fetchall()
    assert len(rows) == 1, f"expected exactly 1 row, got {len(rows)}"
    return dict(zip([d[0] for d in cursor.description], rows[0], strict=True))
