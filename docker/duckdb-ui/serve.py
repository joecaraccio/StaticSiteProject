"""Start DuckDB's web UI over a viewer database.

Two things worth knowing:

* The viewer opens `viewer.duckdb`, not the pipeline's `usually_late.duckdb`.
  Its views read the same Parquet files, so you see the same data, but browsing
  never takes a write lock that would block `pipeline build`.
* The `ui` extension is downloaded on first start and cached in the
  DUCKDB_EXTENSION_DIRECTORY volume, so later starts work offline.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import duckdb

from pipeline import config
from pipeline.metrics import build

PORT = int(os.environ.get("DUCKDB_UI_INTERNAL_PORT", "4212"))


def main() -> int:
    config.PATHS.ensure()
    viewer_db = config.PATHS.clean / "viewer.duckdb"
    con = duckdb.connect(str(viewer_db))

    extension_dir = os.environ.get("DUCKDB_EXTENSION_DIRECTORY")
    if extension_dir:
        Path(extension_dir).mkdir(parents=True, exist_ok=True)
        con.execute(f"SET extension_directory = '{extension_dir}'")

    parquet = sorted((config.PATHS.clean / "operations").glob("operations_*.parquet"))
    if parquet:
        views = build.build_views(con)
        print(f"duckdb-ui: {len(views)} views over {len(parquet)} month(s) of Parquet", flush=True)
    else:
        print(
            "duckdb-ui: no Parquet under /data/clean/operations yet, so no views were "
            "created. Run an ingest, then restart this service.",
            flush=True,
        )

    try:
        con.execute("INSTALL ui")
        con.execute("LOAD ui")
    except duckdb.Error as exc:
        print(
            "duckdb-ui: could not load the 'ui' extension. The first start needs "
            f"network access to extensions.duckdb.org.\n  {exc}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    con.execute(f"SET ui_local_port = {PORT}")
    con.execute("CALL start_ui_server()")
    print(f"duckdb-ui: listening on 127.0.0.1:{PORT} ({viewer_db})", flush=True)

    # start_ui_server() returns immediately; hold the connection open so the
    # server and its views stay alive.
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    raise SystemExit(main())
