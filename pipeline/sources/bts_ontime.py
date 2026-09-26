"""Adapter for the BTS Airline On-Time Performance tables.

Two tables, one download mechanism: both are published as monthly zips in the
same PREZIP directory, so a `Source` value says which table, and every function
here takes one. See DECISIONS.md 2026-09-26 for why both are ingested.

Raw data is immutable (CLAUDE.md): a download is written once, with a sidecar
`.meta.json` carrying the URL, sha256, byte count, fetch timestamp and validator
headers. If BTS later revises a month, the previous bytes are archived beside the
new file rather than overwritten, so nothing is silently lost.

Nothing downloads against a URL template until `pipeline verify-source` has
confirmed it against the live site and written a verification record.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from pipeline import config
from pipeline.models import schema
from pipeline.sources import http


@dataclass(frozen=True)
class Source:
    """One BTS table: where it is published and how its columns map.

    `url_candidates` are tried in order by `verify-source`; `{year}` is 4-digit,
    `{month}` is 1-12 with no zero padding.
    """

    id: str
    title: str
    url_candidates: tuple[str, ...]
    fields: tuple[schema.Field, ...]


#: Flight, route and airport pages. Every flight, including those by regional
#: operators that do not report to BTS themselves. Verified 2026-09-26.
MARKETING = Source(
    id="bts_ontime_marketing_carrier",
    title="Marketing Carrier On-Time Performance (Beginning January 2018)",
    url_candidates=(
        "https://transtats.bts.gov/PREZIP/On_Time_Marketing_Carrier_On_Time_Performance_Beginning_January_2018_{year}_{month}.zip",
    ),
    fields=schema.MARKETING_FIELDS,
)

#: Airline pages only: BTS's official record per reporting carrier. Verified 2026-09-26.
REPORTING = Source(
    id="bts_ontime_reporting_carrier",
    title="Reporting Carrier On-Time Performance (1987-present)",
    url_candidates=(
        "https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip",
        "https://transtats.bts.gov/PREZIP/On_Time_On_Time_Performance_{year}_{month}.zip",
    ),
    fields=schema.REPORTING_FIELDS,
)

SOURCES: tuple[Source, ...] = (MARKETING, REPORTING)


def source_by_id(source_id: str) -> Source:
    for source in SOURCES:
        if source.id == source_id:
            return source
    raise KeyError(f"Unknown source {source_id!r}; known: {', '.join(s.id for s in SOURCES)}")


@dataclass(frozen=True)
class RawRecord:
    """What ended up on disk for one month, and how it got there."""

    source_id: str
    year: int
    month: int
    url: str
    path: str
    sha256: str
    bytes: int
    fetched_at: str
    etag: str | None
    last_modified: str | None
    #: "downloaded" (new bytes), "unchanged" (server said 304 or checksum matched),
    #: or "revised" (content differs from a previous fetch; the old file was archived).
    outcome: str


def month_label(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def parse_month(label: str) -> tuple[int, int]:
    """Parse a `YYYY-MM` label into (year, month)."""
    try:
        year_s, month_s = label.split("-")
        year, month = int(year_s), int(month_s)
    except ValueError as exc:
        raise ValueError(f"Expected a YYYY-MM month label, got {label!r}") from exc
    if not 1 <= month <= 12:
        raise ValueError(f"Month out of range in {label!r}")
    if not 1987 <= year <= 2100:
        raise ValueError(f"Year out of range in {label!r} (BTS coverage starts in 1987)")
    return year, month


def raw_dir(source: Source, year: int) -> Path:
    return config.PATHS.raw / source.id / f"{year:04d}"


def raw_path(source: Source, year: int, month: int) -> Path:
    return raw_dir(source, year) / f"{source.id}_{month_label(year, month)}.zip"


def meta_path(source: Source, year: int, month: int) -> Path:
    return raw_path(source, year, month).with_suffix(".meta.json")


def load_meta(source: Source, year: int, month: int) -> dict | None:
    path = meta_path(source, year, month)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _write_meta(source: Source, record: RawRecord, previous: dict | None) -> None:
    payload = asdict(record)
    history = list(previous.get("history", [])) if previous else []
    if previous and previous.get("sha256") and previous["sha256"] != record.sha256:
        history.append(
            {
                "sha256": previous["sha256"],
                "bytes": previous.get("bytes"),
                "fetched_at": previous.get("fetched_at"),
                "archived_path": previous.get("archived_path"),
            }
        )
    payload["history"] = history
    meta_path(source, record.year, record.month).write_text(json.dumps(payload, indent=2) + "\n")


def fetch_month(
    source: Source,
    year: int,
    month: int,
    *,
    url_template: str,
    force: bool = False,
) -> RawRecord:
    """Download one month of one table, skipping work when nothing changed.

    Uses a conditional GET against the stored ETag/Last-Modified, and also
    compares checksums, so an unchanged file is neither re-downloaded nor
    rewritten.
    """
    config.PATHS.ensure()
    url = url_template.format(year=year, month=month)
    dest = raw_path(source, year, month)
    previous = None if force else load_meta(source, year, month)

    if previous and dest.exists() and not force:
        try:
            response = http.download(
                url,
                dest.with_suffix(".zip.candidate"),
                etag=previous.get("etag"),
                last_modified=previous.get("last_modified"),
            )
        except http.NotModified:
            return RawRecord(
                source_id=source.id,
                year=year,
                month=month,
                url=url,
                path=str(dest),
                sha256=previous["sha256"],
                bytes=previous["bytes"],
                fetched_at=previous["fetched_at"],
                etag=previous.get("etag"),
                last_modified=previous.get("last_modified"),
                outcome="unchanged",
            )
        candidate = dest.with_suffix(".zip.candidate")
        digest = http.sha256_file(candidate)
        if digest == previous["sha256"]:
            candidate.unlink(missing_ok=True)
            return RawRecord(
                source_id=source.id,
                year=year,
                month=month,
                url=url,
                path=str(dest),
                sha256=digest,
                bytes=previous["bytes"],
                fetched_at=previous["fetched_at"],
                etag=response.headers.get("ETag") or previous.get("etag"),
                last_modified=response.headers.get("Last-Modified")
                or previous.get("last_modified"),
                outcome="unchanged",
            )
        # Revised month: keep the old bytes alongside the new ones.
        archived = dest.with_name(f"{dest.stem}.{previous['sha256'][:8]}{dest.suffix}")
        dest.replace(archived)
        previous = {**previous, "archived_path": str(archived)}
        candidate.replace(dest)
        record = RawRecord(
            source_id=source.id,
            year=year,
            month=month,
            url=url,
            path=str(dest),
            sha256=digest,
            bytes=dest.stat().st_size,
            fetched_at=datetime.now(UTC).isoformat(),
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            outcome="revised",
        )
        _write_meta(source, record, previous)
        return record

    response = http.download(url, dest)
    record = RawRecord(
        source_id=source.id,
        year=year,
        month=month,
        url=url,
        path=str(dest),
        sha256=http.sha256_file(dest),
        bytes=dest.stat().st_size,
        fetched_at=datetime.now(UTC).isoformat(),
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
        outcome="downloaded",
    )
    _write_meta(source, record, previous)
    return record
