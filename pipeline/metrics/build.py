"""Create the DuckDB views that the export layer reads.

Nothing is materialized: the views sit on top of `data/clean/**.parquet`, so a
rebuild is just re-running this. `pipeline build` persists them into
data/clean/usually_late.duckdb, which is also what the DuckDB web UI opens.
"""

from __future__ import annotations

import duckdb

from pipeline import config
from pipeline.metrics.definitions import (
    BASE_VIEW,
    GROUPINGS,
    SEASONALITY,
    metric_select,
)


class NoDataError(RuntimeError):
    """No normalized Parquet found; run ingest first."""


def parquet_glob() -> str:
    return (config.PATHS.clean / "operations" / "operations_*.parquet").as_posix()


def _grouped_view(name: str, keys: tuple[str, ...], source: str) -> str:
    key_list = ", ".join(keys)
    return f"""
CREATE OR REPLACE VIEW {name} AS
SELECT
    {key_list},
    {metric_select()}
FROM {source}
GROUP BY {key_list}
"""


def build_views(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Create every view, in dependency order. Returns the view names created."""
    glob = parquet_glob()
    con.execute(BASE_VIEW.format(parquet_glob=glob))
    created = ["operations"]

    # Trailing 12 months = the 12 most recent months present in the data, not the
    # 12 months before today (CLAUDE.md).
    con.execute(
        """
        CREATE OR REPLACE VIEW t12_window AS
        SELECT
            max(flight_month) AS latest_month,
            max(flight_month) - INTERVAL 11 MONTH AS earliest_month
        FROM operations
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW operations_t12 AS
        SELECT o.*
        FROM operations o, t12_window w
        WHERE o.flight_month BETWEEN w.earliest_month AND w.latest_month
        """
    )
    created += ["t12_window", "operations_t12"]

    # Airport pages care about both directions, so each flight appears twice:
    # once as a departure from its origin, once as an arrival at its dest.
    for src, dst in (
        ("operations", "airport_operations"),
        ("operations_t12", "airport_operations_t12"),
    ):
        con.execute(
            f"""
            CREATE OR REPLACE VIEW {dst} AS
            SELECT *, origin AS airport, 'departure' AS role FROM {src}
            UNION ALL
            SELECT *, dest AS airport, 'arrival' AS role FROM {src}
            """
        )
        created.append(dst)

    for name, keys in GROUPINGS.items():
        con.execute(_grouped_view(name, keys, "operations_t12"))
        created.append(name)

    con.execute(_grouped_view("airport_metrics", ("airport", "role"), "airport_operations_t12"))
    created.append("airport_metrics")

    for name, (keys, dims, source) in SEASONALITY.items():
        con.execute(_grouped_view(name, keys + dims, source))
        created.append(name)

    return created


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    config.PATHS.ensure()
    return duckdb.connect(str(config.PATHS.duckdb_file), read_only=read_only)


def rebuild_database() -> tuple[list[str], dict]:
    """Rebuild the persistent DuckDB file's views and return a small summary."""
    if not list((config.PATHS.clean / "operations").glob("operations_*.parquet")):
        raise NoDataError(
            f"No Parquet under {config.PATHS.clean / 'operations'}.\n"
            "Run `pipeline ingest --months YYYY-MM` first."
        )
    con = connect()
    try:
        views = build_views(con)
        summary = dict(
            zip(
                ("rows", "months", "earliest", "latest", "carriers", "routes"),
                con.execute(
                    """
                    SELECT count(*), count(DISTINCT flight_month), min(flight_date),
                           max(flight_date), count(DISTINCT carrier),
                           count(DISTINCT origin || '-' || dest)
                    FROM operations
                    """
                ).fetchone(),
                strict=True,
            )
        )
        return views, summary
    finally:
        con.close()
