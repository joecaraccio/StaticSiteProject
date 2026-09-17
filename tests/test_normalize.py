"""Normalization: raw zip in, canonical Parquet out."""

from __future__ import annotations

import duckdb
import pytest

from pipeline import normalize
from pipeline.models import schema


def test_writes_every_canonical_column_in_order(normalized):
    columns = [
        row[0]
        for row in duckdb.connect()
        .execute(f"DESCRIBE SELECT * FROM read_parquet('{normalized.parquet_path}')")
        .fetchall()
    ]
    assert tuple(columns) == schema.canonical_columns()


def test_row_count_matches_the_source(normalized):
    assert normalized.source_rows == 22
    assert normalized.written_rows == normalized.source_rows


def test_unmapped_source_columns_are_dropped(normalized):
    columns = schema.canonical_columns()
    assert "Tail_Number" not in columns
    assert "tail_number" not in columns


def test_empty_strings_become_null_not_empty_text(con):
    row = con.execute(
        """
        SELECT count(*) FILTER (WHERE actual_arr IS NULL)   AS null_arr,
               count(*) FILTER (WHERE actual_arr = '')      AS empty_arr,
               count(*) FILTER (WHERE cancellation_code IS NULL) AS null_code
        FROM operations
        """
    ).fetchone()
    # 1 cancelled + 1 diverted in 2025-01, plus 3 cancelled in 2023-12 = 5 with no arrival.
    assert row[0] == 5
    assert row[1] == 0
    # Only the 4 cancelled rows carry a code; the diverted one does not.
    assert row[2] == 22 - 4


def test_times_are_stored_as_reported(con):
    """Storage must not reinterpret hhmm; 2400 survives verbatim."""
    values = {r[0] for r in con.execute("SELECT DISTINCT sched_dep FROM operations").fetchall()}
    assert "2400" in values
    assert "0800" in values


def test_lineage_is_recorded(con):
    row = con.execute(
        "SELECT count(DISTINCT source_file), count(*) FILTER (WHERE ingested_at IS NULL) "
        "FROM operations"
    ).fetchone()
    assert row[0] == 1
    assert row[1] == 0


def test_missing_raw_file_is_an_error(data_root):
    with pytest.raises(FileNotFoundError):
        normalize.normalize_month(2024, 6)


def test_required_column_absent_is_rejected():
    """A source that drops a required column must fail loudly, not silently null it."""
    header = [f.source for f in schema.OPERATIONS_FIELDS if f.source != "Origin"]
    with pytest.raises(ValueError, match="Origin"):
        normalize._select_expression(header)


def test_absent_optional_column_becomes_typed_null():
    header = [f.source for f in schema.OPERATIONS_FIELDS if f.source != "SecurityDelay"]
    expression = normalize._select_expression(header)
    assert "CAST(NULL AS DOUBLE) AS security_delay" in expression
