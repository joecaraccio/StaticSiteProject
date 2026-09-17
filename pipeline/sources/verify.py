"""Confirm the BTS source against the live site, and gate the pipeline on it.

CLAUDE.md: "Verify before hardcoding. Download URLs, file formats, and column
names must be confirmed against the live source before code depends on them."

This module makes that rule mechanical rather than aspirational:

* `verify()` probes the candidate URLs, downloads one month, reads the real CSV
  header out of the zip, and diffs it against the candidate mapping in
  `pipeline.models.schema`.
* It writes `data/verification/<source>.json` recording exactly what was seen.
* `require_verified()` is called by `ingest`, which refuses to run without a
  record that matches the URL template and schema it is about to use.

So an unverified guess cannot quietly become a dependency.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pipeline import config
from pipeline.models import schema
from pipeline.sources import bts_ontime, http


class NotVerified(Exception):
    """The source has not been confirmed against the live site."""


@dataclass
class ProbeResult:
    url_template: str
    url: str
    ok: bool
    status: int | None = None
    content_type: str | None = None
    content_length: str | None = None
    error: str | None = None


@dataclass
class VerificationRecord:
    source_id: str
    verified_at: str
    month: str
    url_template: str
    url: str
    schema_fingerprint: str
    archive_members: list[str] = field(default_factory=list)
    csv_member: str = ""
    delimiter: str = ""
    encoding: str = ""
    header: list[str] = field(default_factory=list)
    matched_columns: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)
    unmapped_source_columns: list[str] = field(default_factory=list)
    probes: list[dict] = field(default_factory=list)
    raw_sha256: str = ""


def record_path(source_id: str = bts_ontime.SOURCE_ID) -> Path:
    return config.PATHS.verification / f"{source_id}.json"


def schema_fingerprint() -> str:
    """A stable digest of the candidate mapping.

    If the mapping changes, an old verification record no longer certifies it and
    the source must be re-verified.
    """
    import hashlib

    payload = "|".join(f"{f.name}={f.source}:{f.sql_type}" for f in schema.OPERATIONS_FIELDS)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def probe_candidates(year: int, month: int) -> list[ProbeResult]:
    """HEAD each candidate URL and report what the live site says."""
    results: list[ProbeResult] = []
    for template in bts_ontime.URL_CANDIDATES:
        url = template.format(year=year, month=month)
        try:
            response = http.head(url)
        except Exception as exc:  # any failure just means "not this candidate"
            results.append(
                ProbeResult(template, url, ok=False, error=f"{type(exc).__name__}: {exc}")
            )
            continue
        content_type = response.headers.get("Content-Type", "")
        ok = response.status in (200, 206) and "html" not in content_type.lower()
        results.append(
            ProbeResult(
                template,
                url,
                ok=ok,
                status=response.status,
                content_type=content_type,
                content_length=response.headers.get("Content-Length"),
            )
        )
    return results


def _read_header(archive: Path) -> tuple[str, list[str], str, str]:
    """Return (member name, header columns, delimiter, encoding) from the zip."""
    with zipfile.ZipFile(archive) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not members:
            raise NotVerified(f"No .csv member inside {archive.name}: {zf.namelist()}")
        member = members[0]
        with zf.open(member) as fh:
            first = fh.read(64 * 1024)

    encoding = "utf-8-sig"
    try:
        text = first.decode(encoding)
    except UnicodeDecodeError:
        encoding = "latin-1"
        text = first.decode(encoding)

    line = text.splitlines()[0] if text.splitlines() else ""
    try:
        delimiter = csv.Sniffer().sniff(line, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    header = next(csv.reader(io.StringIO(line), delimiter=delimiter), [])
    return member, [c.strip() for c in header], delimiter, encoding


def verify(month: str, *, force_download: bool = False) -> VerificationRecord:
    """Probe, download and inspect one month; write a verification record."""
    year, month_num = bts_ontime.parse_month(month)
    config.PATHS.ensure()

    probes = probe_candidates(year, month_num)
    winner = next((p for p in probes if p.ok), None)
    if winner is None:
        detail = "\n".join(f"  {p.url} -> {p.status or p.error}" for p in probes)
        raise NotVerified(
            "No candidate BTS URL responded with a downloadable file:\n"
            f"{detail}\n"
            "Open https://transtats.bts.gov/DatabaseInfo.asp?QO_VQ=EFD, find the current\n"
            "bulk-download link, and add it to URL_CANDIDATES in pipeline/sources/bts_ontime.py."
        )

    raw = bts_ontime.fetch_month(
        year, month_num, url_template=winner.url_template, force=force_download
    )
    member, header, delimiter, encoding = _read_header(Path(raw.path))

    by_source = schema.by_source_name()
    present = set(header)
    matched = [c for c in header if c in by_source]
    missing_required = [
        f.source for f in schema.OPERATIONS_FIELDS if f.required and f.source not in present
    ]
    missing_optional = [
        f.source for f in schema.OPERATIONS_FIELDS if not f.required and f.source not in present
    ]
    unmapped = [c for c in header if c and c not in by_source]

    record = VerificationRecord(
        source_id=bts_ontime.SOURCE_ID,
        verified_at=datetime.now(UTC).isoformat(),
        month=month,
        url_template=winner.url_template,
        url=winner.url,
        schema_fingerprint=schema_fingerprint(),
        archive_members=sorted(zipfile.ZipFile(raw.path).namelist()),
        csv_member=member,
        delimiter=delimiter,
        encoding=encoding,
        header=header,
        matched_columns=matched,
        missing_required=missing_required,
        missing_optional=missing_optional,
        unmapped_source_columns=unmapped,
        probes=[asdict(p) for p in probes],
        raw_sha256=raw.sha256,
    )
    record_path().write_text(json.dumps(asdict(record), indent=2) + "\n")
    return record


def load_record(source_id: str = bts_ontime.SOURCE_ID) -> VerificationRecord:
    path = record_path(source_id)
    if not path.exists():
        raise NotVerified(
            f"No verification record at {path}.\n"
            "Run `pipeline verify-source --month YYYY-MM` first (it needs network access\n"
            "to transtats.bts.gov). Ingest will not run against an unverified source."
        )
    return VerificationRecord(**json.loads(path.read_text()))


def require_verified(source_id: str = bts_ontime.SOURCE_ID) -> VerificationRecord:
    """Return the verification record, or explain precisely why it does not apply."""
    record = load_record(source_id)
    if record.missing_required:
        raise NotVerified(
            "The last verification found required columns missing from the source: "
            f"{', '.join(record.missing_required)}.\n"
            "Fix the mapping in pipeline/models/schema.py and re-verify."
        )
    current = schema_fingerprint()
    if record.schema_fingerprint != current:
        raise NotVerified(
            "The canonical schema changed since the source was verified "
            f"({record.schema_fingerprint} -> {current}).\n"
            "Re-run `pipeline verify-source --month YYYY-MM`."
        )
    return record


def as_markdown(record: VerificationRecord) -> str:
    """Render the record as a DATA_NOTES.md block, ready to paste."""
    lines = [
        f"### Verified {record.verified_at[:10]} · {record.source_id}",
        "",
        f"- **URL template:** `{record.url_template}`",
        f"- **Checked with month:** {record.month} (sha256 `{record.raw_sha256[:16]}…`)",
        f"- **Archive members:** {', '.join(record.archive_members) or '(none)'}",
        f"- **CSV member:** `{record.csv_member}`",
        f"- **Delimiter:** `{record.delimiter}` · **Encoding:** `{record.encoding}`",
        f"- **Columns in source:** {len(record.header)}",
        f"- **Mapped:** {len(record.matched_columns)} · "
        f"**Missing required:** {len(record.missing_required)} · "
        f"**Missing optional:** {len(record.missing_optional)}",
        "",
        "| Canonical field | Source column | Type | Present | Notes |",
        "|---|---|---|---|---|",
    ]
    present = set(record.header)
    for f in schema.OPERATIONS_FIELDS:
        mark = "yes" if f.source in present else ("**MISSING**" if f.required else "no")
        lines.append(f"| `{f.name}` | `{f.source}` | {f.sql_type} | {mark} | {f.note} |")
    if record.unmapped_source_columns:
        lines += [
            "",
            f"Unmapped source columns ({len(record.unmapped_source_columns)}): "
            + ", ".join(f"`{c}`" for c in record.unmapped_source_columns),
        ]
    return "\n".join(lines) + "\n"
