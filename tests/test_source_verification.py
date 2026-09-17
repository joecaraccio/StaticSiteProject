"""The verification gate: no verified record, no ingest.

None of these tests touch the network. They check the gate's logic, which is what
stops an unverified guess from becoming a dependency.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from pipeline.models import schema
from pipeline.sources import bts_ontime, verify


def _write_record(**overrides) -> verify.VerificationRecord:
    record = verify.VerificationRecord(
        source_id=bts_ontime.SOURCE_ID,
        verified_at="2026-01-15T00:00:00+00:00",
        month="2025-01",
        url_template=bts_ontime.URL_CANDIDATES[0],
        url="https://example.invalid/file.zip",
        schema_fingerprint=verify.schema_fingerprint(),
        header=[f.source for f in schema.OPERATIONS_FIELDS],
        matched_columns=[f.source for f in schema.OPERATIONS_FIELDS],
        csv_member="sample.csv",
        delimiter=",",
        encoding="utf-8-sig",
    )
    for key, value in overrides.items():
        setattr(record, key, value)
    verify.record_path().write_text(json.dumps(asdict(record), indent=2))
    return record


def test_no_record_blocks_ingest(data_root):
    with pytest.raises(verify.NotVerified, match="No verification record"):
        verify.require_verified()


def test_complete_record_passes(data_root):
    _write_record()
    assert verify.require_verified().url_template == bts_ontime.URL_CANDIDATES[0]


def test_missing_required_column_blocks_ingest(data_root):
    _write_record(missing_required=["Origin", "Dest"])
    with pytest.raises(verify.NotVerified, match="Origin, Dest"):
        verify.require_verified()


def test_schema_change_invalidates_an_old_record(data_root):
    """Editing the mapping must force re-verification, not silently reuse the old one."""
    _write_record(schema_fingerprint="0000000000000000")
    with pytest.raises(verify.NotVerified, match="schema changed"):
        verify.require_verified()


def test_fingerprint_tracks_the_mapping(monkeypatch):
    before = verify.schema_fingerprint()
    changed = (
        *schema.OPERATIONS_FIELDS[:-1],
        schema.Field("distance", "DistanceRenamed", "DOUBLE", required=False),
    )
    monkeypatch.setattr(schema, "OPERATIONS_FIELDS", changed)
    assert verify.schema_fingerprint() != before


def test_markdown_flags_missing_required_columns(data_root):
    record = _write_record(header=["FlightDate"], missing_required=["Origin"])
    notes = verify.as_markdown(record)
    assert "**MISSING**" in notes
    assert "`flight_date`" in notes
    assert "| Canonical field | Source column |" in notes


# --- month parsing ---------------------------------------------------------


@pytest.mark.parametrize("label,expected", [("2025-01", (2025, 1)), ("1987-10", (1987, 10))])
def test_parse_month(label, expected):
    assert bts_ontime.parse_month(label) == expected


@pytest.mark.parametrize("label", ["2025-13", "2025-00", "1986-01", "202501", "", "abc-01"])
def test_parse_month_rejects_nonsense(label):
    with pytest.raises(ValueError):
        bts_ontime.parse_month(label)
