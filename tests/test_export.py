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
    # The summary gate is now live; only the similarity gate remains skipped.
    assert not any(s.startswith("summary") for s in doc["gate"]["skipped_gates"])
    assert any(s.startswith("similarity") for s in doc["gate"]["skipped_gates"])


def test_pages_carry_rule_based_summary_sentences(con):
    export(con)
    summary = read("pages/airlines/AA.json")["summary"]
    assert summary["matched_rules"][0] == "headline"
    assert summary["sentences"][0].startswith("AA is usually late")
    # The text must come from the rule engine, never from a language model.
    assert len(summary["sentences"]) == len(summary["matched_rules"])


def test_flight_pages_compare_themselves_to_their_route(con):
    export(con)
    sentences = " ".join(read("pages/flights/AA/100/BOS-LGA.json")["summary"]["sentences"])
    assert "the BOS to LGA route" in sentences
    assert "DL 200 is the most reliable option" in sentences


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


# --- comparison with alternatives (PLAN.md §7 required block) --------------


def test_flight_pages_carry_the_other_flights_on_their_route(con):
    export(con)
    doc = read("pages/flights/AA/100/BOS-LGA.json")
    alts = doc["alternatives"]
    assert {a["carrier"] for a in alts} == {"AA", "DL"}
    assert all(a["url"].endswith("BOS-LGA") for a in alts)


def test_the_page_own_flight_is_included_and_marked(con):
    export(con)
    alts = read("pages/flights/AA/100/BOS-LGA.json")["alternatives"]
    marked = [a for a in alts if a["is_this_page"]]
    assert len(marked) == 1
    assert marked[0]["carrier"] == "AA" and marked[0]["flight_number"] == "100"


def test_alternatives_are_ordered_best_on_time_first(con):
    export(con)
    alts = read("pages/flights/AA/100/BOS-LGA.json")["alternatives"]
    rates = [a["on_time_rate"] for a in alts if a["on_time_rate"] is not None]
    assert rates == sorted(rates, reverse=True)
    assert alts[0]["carrier"] == "DL"  # 100% on time beats AA's 37.5%


def test_alternatives_carry_a_typical_departure_time(con):
    export(con)
    alts = read("pages/flights/AA/100/BOS-LGA.json")["alternatives"]
    times = {a["carrier"]: a["typical_sched_dep"] for a in alts}
    assert times["DL"] == "1730"
    assert times["AA"] == "0800"  # the single 2400 row does not beat eight 0800s


def test_airline_and_airport_pages_have_no_alternatives_block(con):
    export(con)
    for page in ("pages/airlines/AA.json", "pages/airports/BOS.json"):
        assert read(page)["alternatives"] == []


def test_a_route_with_no_flights_left_fails_the_required_block_gate(con):
    """An empty alternatives list on a flight or route page is a missing block."""
    doc = {
        "page_type": "route",
        "alternatives": [],
        "headline_stats": {"on_time_rate": 0.8},
        "monthly_series": [{}],
        "delay_causes": {"total_minutes": 1},
        "delay_distribution": {"shares": {"on_time": 1.0}},
    }
    assert "alternatives" in pages._missing_blocks(doc)
    doc["page_type"] = "airline"
    assert "alternatives" not in pages._missing_blocks(doc)


# --- demo builds -----------------------------------------------------------


def test_real_exports_carry_no_demo_notice(con):
    export(con)
    assert read("pages/airlines/AA.json")["demo_notice"] is None
    assert json.loads((config.PATHS.export / "manifest.json").read_text())["demo_notice"] is None


def test_demo_notice_stamps_every_page_and_the_manifest(con):
    notice = "Mockup: synthetic figures."
    pages.export_all(con=con, today=TODAY, demo_notice=notice)
    assert read("pages/airlines/AA.json")["demo_notice"] == notice
    assert read("pages/airports/BOS.json")["demo_notice"] == notice
    assert json.loads((config.PATHS.export / "manifest.json").read_text())["demo_notice"] == notice
