"""Turn a raw monthly zip into one Parquet file with canonical column names.

All transformation happens here, downstream of immutable raw storage. DuckDB does
the CSV reading and Parquet writing natively, so there is no pandas/pyarrow step.

Each source gets its own directory, `data/clean/<source id>/`, because the two
tables mean different things by `carrier` and must never be read as one.

Times are stored as reported (zero-padded hhmm strings, "2400" possible in actual
times). Interpreting them is left to the metrics layer, so storage never bakes in
an interpretation.
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
    source_id: str
    month: str
    parquet_path: str
    source_rows: int
    written_rows: int
    columns: int


def clean_dir(source: bts_ontime.Source) -> Path:
    return config.PATHS.clean / source.id


def parquet_glob(source: bts_ontime.Source) -> str:
    return (clean_dir(source) / "operations_*.parquet").as_posix()


def parquet_path(source: bts_ontime.Source, year: int, month: int) -> Path:
    return clean_dir(source) / f"operations_{bts_ontime.month_label(year, month)}.parquet"


def _sql_literal(value: str) -> str:
    """Quote a string for inlining into SQL, escaping embedded quotes."""
    return "'" + value.replace("'", "''") + "'"


def _select_expression(fields: tuple[schema.Field, ...], header: list[str]) -> str:
    """Build the canonical SELECT list against the columns actually present.

    Header names are matched after trimming, because BTS ships at least one with
    a trailing space (`"Operating_Airline "`); the verifier matches the same way.
    A required column that is absent is a hard error: the caller has already
    checked the verification record, so reaching here means the source changed.
    """
    actual = {h.strip(): h for h in header}
    parts: list[str] = []
    for f in fields:
        column = actual.get(f.source)
        if column is None:
            if f.required:
                raise ValueError(f"Required source column {f.source!r} not in file header")
            parts.append(f"CAST(NULL AS {f.sql_type}) AS {f.name}")
            continue
        quoted = '"' + column.replace('"', '""') + '"'
        if f.sql_type == "VARCHAR":
            # NULLIF collapses the empty strings BTS uses for absent values.
            parts.append(f"NULLIF(TRIM(CAST({quoted} AS VARCHAR)), '') AS {f.name}")
        else:
            parts.append(f"TRY_CAST({quoted} AS {f.sql_type}) AS {f.name}")
    return ",\n    ".join(parts)


def normalize_month(
    source: bts_ontime.Source,
    year: int,
    month: int,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
) -> NormalizeResult:
    """Extract the CSV from the month's raw zip and write canonical Parquet."""
    raw = bts_ontime.raw_path(source, year, month)
    if not raw.exists():
        raise FileNotFoundError(
            f"No raw {source.id} file for {bts_ontime.month_label(year, month)}: {raw}"
        )

    out = parquet_path(source, year, month)
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
                return _write_parquet(con, source, csv_path, out, year, month, raw.name)
    finally:
        if owns_connection:
            con.close()


def _write_parquet(
    con: duckdb.DuckDBPyConnection,
    source: bts_ontime.Source,
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
                {_select_expression(source.fields, header)},
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
        source_id=source.id,
        month=bts_ontime.month_label(year, month),
        parquet_path=str(out),
        source_rows=source_rows,
        written_rows=written_rows,
        columns=len(schema.canonical_columns(source.fields)),
    )


def available_months(source: bts_ontime.Source) -> list[str]:
    """Months present in data/clean for one source, oldest first."""
    directory = clean_dir(source)
    if not directory.exists():
        return []
    return sorted(
        p.stem.removeprefix("operations_") for p in directory.glob("operations_*.parquet")
    )
