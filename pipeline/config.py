"""Filesystem layout and runtime settings.

Every path is derived from one root so the pipeline behaves the same on a laptop
and inside the container, where DATA_ROOT is a mounted volume.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _root() -> Path:
    env = os.environ.get("DATA_ROOT")
    if env:
        return Path(env)
    # Default to <repo>/data when running from a source checkout.
    return Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Paths:
    """Resolved data directories. `data/` is gitignored in full."""

    root: Path

    @property
    def raw(self) -> Path:
        """Downloads exactly as received. Never modified, never rewritten."""
        return self.root / "raw"

    @property
    def clean(self) -> Path:
        """Normalized Parquet, safe to delete and rebuild from raw."""
        return self.root / "clean"

    @property
    def export(self) -> Path:
        """One JSON document per page, plus the gate report."""
        return self.root / "export"

    @property
    def verification(self) -> Path:
        """Source verification records (see pipeline.sources.verify)."""
        return self.root / "verification"

    @property
    def duckdb_file(self) -> Path:
        return self.root / "clean" / "usually_late.duckdb"

    def ensure(self) -> None:
        for p in (self.raw, self.clean, self.export, self.verification):
            p.mkdir(parents=True, exist_ok=True)


PATHS = Paths(root=_root())

# Be polite to the source: one request at a time, with a gap between them.
DOWNLOAD_DELAY_SECONDS = float(os.environ.get("DOWNLOAD_DELAY_SECONDS", "2.0"))
DOWNLOAD_TIMEOUT_SECONDS = float(os.environ.get("DOWNLOAD_TIMEOUT_SECONDS", "120"))
USER_AGENT = os.environ.get(
    "PIPELINE_USER_AGENT",
    "usually-late-pipeline/0.1 (personal project; contact via repository)",
)
