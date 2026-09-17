"""Export: metrics in, one JSON document per page out, gated on the way."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pipeline import config
from pipeline.export import pages

#: A month after the fixture's last flight date, i.e. ordinary BTS publishing lag.
#: Pinned so the data-age gate does not change these tests as time passes.
TODAY = date(2025, 2, 15)


def export(con) -> pages.ExportResult:
    return pages.export_all(con=con, today=TODAY)


def read(result_relative: str) -> dict:
    return json.loads((config.PATHS.export / result_relative).read_text())


def test_writes_a_document_per_surviving_page(con):
    result = export(con)
    manifest = json.loads(Path(result.manifest_path).read_text())
    assert result.written == len(manifest["pages"])
    for entry in manifest["pages"]:
        assert (config.PATHS.export / entry["file"]).exists()


def test_every_page_type_is_considered(con):
    result = export(con)
    assert set(result.by_type) == {"flight", "route", "airport", "airline"}


def test_url_patterns_match_the_plan(con):
    export(con)
    manifest = json.loads((config.PATHS.export / "manifest.json").read_text())
    written = {e["url"] for e in manifest["pages"]}
    assert "/airlines/AA" in written
    assert "/airports/BOS" in written
    # The patterns themselves, so a change to PLAN.md §7 fails a test here.
    assert pages.PAGE_TYPES["flight"][2] == "/flights/{carrier}/{flight_number}/{origin}-{dest}"
    assert pages.PAGE_TYPES["route"][2] == "/routes/{origin}-{dest}"


def test_flight_thresholds_split_three_ways(con):
    """AA 100 has 10 operations (noindex band), DL 200 has 5 and UA 300 has 4
    (both below the drop threshold). None reach the 30 needed to publish."""
    result = export(con)
    assert result.by_type["flight"] == {"publish": 0, "noindex": 1, "drop": 2}
    assert (config.PATHS.export / "pages" / "flights" / "AA" / "100" / "BOS-LGA.json").exists()
    assert not (config.PATHS.export / "pages" / "flights" / "DL").exists()


def test_airline_pages_survive_at_any_volume(con):
    """Reporting-carrier airline pages publish regardless of sample size."""
    result = export(con)
    assert result.by_type["airline"] == {"publish": 3, "noindex": 0, "drop": 0}


def test_a_carrier_with_no_delays_is_not_dropped(con):
    """DL has five on-time flights and so zero attributed delay minutes. Zero is
    real data, not a missing block."""
    export(con)
    doc = read("pages/airlines/DL.json")
    assert doc["delay_causes"]["total_minutes"] == 0
    assert doc["delay_causes"]["shares"] is None
    assert doc["gate"]["outcome"] == "publish"


def test_routes_below_sixty_operations_are_dropped(con):
    result = export(con)
    assert result.by_type["route"] == {"publish": 0, "noindex": 0, "drop": 2}


def test_quiet_airports_are_noindexed_not_dropped(con):
    result = export(con)
    assert result.by_type["airport"] == {"publish": 0, "noindex": 2, "drop": 0}
    assert read("pages/airports/BOS.json")["gate"]["noindex"] is True


def test_document_carries_attribution_and_data_period(con):
    export(con)
    doc = read("pages/airlines/AA.json")
    assert doc["source"]["attribution"].startswith("U.S. Department of Transportation")
    assert doc["data_period"] == {"start": "2023-12-01", "end": "2025-01-17"}
    assert doc["schema_version"] == pages.SCHEMA_VERSION


def test_headline_stats_match_the_metrics_view(con):
    export(con)
    doc = read("pages/airlines/DL.json")
    assert doc["headline_stats"]["ops_scheduled"] == 5
    assert doc["headline_stats"]["on_time_rate"] == 1.0


def test_delay_cause_shares_state_their_basis_and_sum_to_one(con):
    export(con)
    doc = read("pages/airlines/AA.json")
    causes = doc["delay_causes"]
    assert causes["basis"] == "attributed_delay_minutes"
    assert sum(causes["shares"].values()) == 1.0
    assert causes["total_minutes"] == 505


def test_delay_distribution_shares_sum_to_one(con):
    export(con)
    doc = read("pages/airlines/AA.json")
    shares = doc["delay_distribution"]["shares"]
    assert abs(sum(shares.values()) - 1.0) < 1e-9


def test_monthly_series_is_present_and_ordered(con):
    export(con)
    doc = read("pages/airlines/AA.json")
    months = [m["month"] for m in doc["monthly_series"]]
    assert months == sorted(months)
    assert "2025-01" in months


def test_gate_outcome_is_recorded_on_the_document(con):
    export(con)
    doc = read("pages/airlines/AA.json")
    assert doc["gate"]["outcome"] in ("publish", "noindex")
    assert isinstance(doc["gate"]["noindex"], bool)
    # The M6 gates must be visible as skipped, not absent.
    assert any("summary" in s for s in doc["gate"]["skipped_gates"])


def test_summary_field_exists_as_null_until_m6(con):
    export(con)
    assert read("pages/airlines/AA.json")["summary"] is None


def test_gate_report_lists_every_candidate_with_reasons(con):
    import csv

    result = export(con)
    with open(result.report_path) as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == sum(sum(c.values()) for c in result.by_type.values())
    assert all(row["reasons"] for row in rows)
    dropped = [r for r in rows if r["outcome"] == "drop"]
    assert len(dropped) == 4  # 2 flights + 2 routes below their drop thresholds
    assert all("trailing 12 months" in r["reasons"] for r in dropped)


def test_manifest_totals_agree_with_the_report(con):
    result = export(con)
    manifest = json.loads(Path(result.manifest_path).read_text())
    assert manifest["totals"]["drop"] == result.dropped
    assert manifest["totals"]["publish"] + manifest["totals"]["noindex"] == result.written
