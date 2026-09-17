"""Turn a raw monthly zip into one Parquet file with canonical column names.

All transformation happens here, downstream of immutable raw storage. DuckDB does
the CSV reading and Parquet writing natively, so there is no pandas/pyarrow step.

Times are stored as reported (trimmed strings, e.g. "800", "2400"). Interpreting
hhmm is deliberately left to the metrics layer: the meaning of those fields is
still an open item on the DATA_NOTES.md verification checklist, and guessing here
would bake an assumption into storage.
"""

from __future__ import annotations

import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from pipeline import config
from pipeline.models import schema
from pipeline.sources import bts_ontime


@dataclass(frozen=True)
class NormalizeResult:
    month: str
    parquet_path: str
    source_rows: int
    written_rows: int
    columns: int


def parquet_path(year: int, month: int) -> Path:
    return (
        config.PATHS.clean
        / "operations"
        / f"operations_{bts_ontime.month_label(year, month)}.parquet"
    )


def _sql_literal(value: str) -> str:
    """Quote a string for inlining into SQL, escaping embedded quotes."""
    return "'" + value.replace("'", "''") + "'"


def _select_expression(header: list[str]) -> str:
    """Build the canonical SELECT list against the columns actually present.

    A required column that is absent is a hard error: the caller has already
    checked the verification record, so reaching here means the source changed.
    """
    present = set(header)
    parts: list[str] = []
    for f in schema.OPERATIONS_FIELDS:
        if f.source not in present:
            if f.required:
                raise ValueError(f"Required source column {f.source!r} not in file header")
            parts.append(f"CAST(NULL AS {f.sql_type}) AS {f.name}")
            continue
        if f.sql_type == "VARCHAR":
            # NULLIF collapses the empty strings BTS uses for absent values.
            parts.append(f"NULLIF(TRIM(CAST(\"{f.source}\" AS VARCHAR)), '') AS {f.name}")
        else:
            parts.append(f'TRY_CAST("{f.source}" AS {f.sql_type}) AS {f.name}')
    return ",\n    ".join(parts)


def normalize_month(
    year: int, month: int, *, con: duckdb.DuckDBPyConnection | None = None
) -> NormalizeResult:
    """Extract the CSV from the month's raw zip and write canonical Parquet."""
    raw = bts_ontime.raw_path(year, month)
    if not raw.exists():
        raise FileNotFoundError(f"No raw file for {bts_ontime.month_label(year, month)}: {raw}")

    out = parquet_path(year, month)
    out.parent.mkdir(parents=True, exist_ok=True)
    owns_connection = con is None
    con = con or duckdb.connect()

    try:
        with zipfile.ZipFile(raw) as zf:
            members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not members:
                raise ValueError(f"No .csv member in {raw}")
            with tempfile.TemporaryDirectory(prefix="usually-late-") as tmpdir:
                csv_path = Path(zf.extract(members[0], path=tmpdir))
                return _write_parquet(con, csv_path, out, year, month, raw.name)
    finally:
        if owns_connection:
            con.close()


def _write_parquet(
    con: duckdb.DuckDBPyConnection,
    csv_path: Path,
    out: Path,
    year: int,
    month: int,
    source_file: str,
) -> NormalizeResult:
    # DuckDB cannot prepare parameters inside CREATE VIEW, so the path is inlined.
    # `all_varchar` keeps every column a string: casting happens explicitly below,
    # so a stray value can never silently change a column's inferred type.
    con.execute(
        "CREATE OR REPLACE TEMP VIEW src AS SELECT * FROM "
        f"read_csv({_sql_literal(csv_path.as_posix())}, header = true, "
        "all_varchar = true, sample_size = -1)"
    )
    header = [row[0] for row in con.execute("DESCRIBE src").fetchall()]
    source_rows = con.execute("SELECT count(*) FROM src").fetchone()[0]

    ingested_at = datetime.now(UTC)
    con.execute(
        f"""
        COPY (
            SELECT
                {_select_expression(header)},
                ? AS source_file,
                ? AS ingested_at
            FROM src
        ) TO {_sql_literal(out.as_posix())} (FORMAT PARQUET, COMPRESSION ZSTD)
        """,  # column list comes from the vetted canonical schema, not user input
        [source_file, ingested_at],
    )
    written_rows = con.execute("SELECT count(*) FROM read_parquet(?)", [out.as_posix()]).fetchone()[
        0
    ]
    return NormalizeResult(
        month=bts_ontime.month_label(year, month),
        parquet_path=str(out),
        source_rows=source_rows,
        written_rows=written_rows,
        columns=len(schema.canonical_columns()),
    )


def available_months() -> list[str]:
    """Months present in data/clean, oldest first."""
    directory = config.PATHS.clean / "operations"
    if not directory.exists():
        return []
    months = []
    for path in directory.glob("operations_*.parquet"):
        months.append(path.stem.removeprefix("operations_"))
    return sorted(months)
