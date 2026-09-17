"""Usually Late data pipeline.

Stages: ingest (raw, immutable) -> normalize (Parquet) -> metrics (DuckDB views)
-> export (page JSON) -> gates (publish/noindex/drop).
"""

__version__ = "0.1.0"
