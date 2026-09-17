"""Shared fixtures.

Every test runs against a throwaway DATA_ROOT so nothing touches a real
`data/` directory, and the synthetic sample is pushed through the *real* code
path — zipped, normalized, then queried — rather than loaded directly.
"""

from __future__ import annotations

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


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> config.Paths:
    """Point the pipeline at an empty temporary data directory."""
    paths = config.Paths(root=tmp_path / "data")
    monkeypatch.setattr(config, "PATHS", paths)
    monkeypatch.setattr(config, "DOWNLOAD_DELAY_SECONDS", 0.0)
    paths.ensure()
    return paths


@pytest.fixture
def raw_fixture_zip(data_root: config.Paths) -> Path:
    """Stage the synthetic CSV as a raw monthly zip, the way ingest would find it."""
    year, month = bts_ontime.parse_month(REFERENCE_MONTH)
    target = bts_ontime.raw_path(year, month)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(FIXTURE_CSV, arcname="On_Time_Reporting_Carrier_Sample.csv")
    return target


@pytest.fixture
def normalized(raw_fixture_zip: Path) -> normalize.NormalizeResult:
    year, month = bts_ontime.parse_month(REFERENCE_MONTH)
    return normalize.normalize_month(year, month)


@pytest.fixture
def con(normalized: normalize.NormalizeResult) -> duckdb.DuckDBPyConnection:
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
