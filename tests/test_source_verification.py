"""The verification gate: no verified record, no ingest.

None of these tests touch the network. They check the gate's logic, which is what
stops an unverified guess from becoming a dependency.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from pipeline import cli
from pipeline.models import schema
from pipeline.sources import bts_ontime, verify

SOURCE = bts_ontime.REPORTING

#: From data/verification/bts_ontime_reporting_carrier.json, written by the live check.
REPORTING_FINGERPRINT_2026_09_26 = "6538f0f85566a6d9"


def _write_record(source: bts_ontime.Source = SOURCE, **overrides) -> verify.VerificationRecord:
    record = verify.VerificationRecord(
        source_id=source.id,
        verified_at="2026-01-15T00:00:00+00:00",
        month="2025-01",
        url_template=source.url_candidates[0],
        url="https://example.invalid/file.zip",
        schema_fingerprint=verify.schema_fingerprint(source),
        header=[f.source for f in source.fields],
        matched_columns=[f.source for f in source.fields],
        csv_member="sample.csv",
        delimiter=",",
        encoding="utf-8-sig",
    )
    for key, value in overrides.items():
        setattr(record, key, value)
    verify.record_path(source).write_text(json.dumps(asdict(record), indent=2))
    return record


def test_no_record_blocks_ingest(data_root):
    with pytest.raises(verify.NotVerified, match="No verification record"):
        verify.require_verified(SOURCE)


def test_complete_record_passes(data_root):
    _write_record()
    assert verify.require_verified(SOURCE).url_template == SOURCE.url_candidates[0]


def test_missing_required_column_blocks_ingest(data_root):
    _write_record(missing_required=["Origin", "Dest"])
    with pytest.raises(verify.NotVerified, match="Origin, Dest"):
        verify.require_verified(SOURCE)


def test_schema_change_invalidates_an_old_record(data_root):
    """Editing the mapping must force re-verification, not silently reuse the old one."""
    _write_record(schema_fingerprint="0000000000000000")
    with pytest.raises(verify.NotVerified, match=r"mapping .* changed"):
        verify.require_verified(SOURCE)


def test_fingerprint_tracks_the_mapping():
    changed = bts_ontime.Source(
        id=SOURCE.id,
        title=SOURCE.title,
        url_candidates=SOURCE.url_candidates,
        fields=(
            *SOURCE.fields[:-1],
            schema.Field("distance", "DistanceRenamed", "DOUBLE", required=False),
        ),
    )
    assert verify.schema_fingerprint(changed) != verify.schema_fingerprint(SOURCE)


def test_reporting_fingerprint_survived_the_split():
    """Splitting the schema into two tables must not change the reporting mapping.

    This is the fingerprint recorded when the reporting table was verified against
    the live site on 2026-09-26. If it changes, the mapping changed, and the
    source needs re-verifying rather than this number updating.
    """
    assert verify.schema_fingerprint(bts_ontime.REPORTING) == REPORTING_FINGERPRINT_2026_09_26


def test_each_source_has_its_own_record(data_root):
    _write_record(bts_ontime.MARKETING)
    verify.require_verified(bts_ontime.MARKETING)
    with pytest.raises(verify.NotVerified, match=bts_ontime.REPORTING.id):
        verify.require_verified(bts_ontime.REPORTING)


def test_ingest_refuses_until_every_source_is_verified(data_root, capsys):
    """Pages read both tables, so one verified source is not enough to ingest."""
    _write_record(bts_ontime.REPORTING)
    assert cli.main(["ingest", "--months", "2025-01"]) == 2
    assert bts_ontime.MARKETING.id in capsys.readouterr().err


def test_markdown_flags_missing_required_columns(data_root):
    record = _write_record(header=["FlightDate"], missing_required=["Origin"])
    notes = verify.as_markdown(SOURCE, record)
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
