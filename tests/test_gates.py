"""Gate rules, against the thresholds in docs/PLAN.md section 7."""

from __future__ import annotations

from datetime import date

import pytest

from pipeline.gates.rules import (
    Outcome,
    PageCandidate,
    Thresholds,
    evaluate,
    report_rows,
    stale_cutoff,
    summarize,
)

PERIOD_END = date(2026, 1, 31)
TODAY = date(2026, 3, 1)  # ~30 days after the data period, i.e. normal BTS lag


def candidate(**kw) -> PageCandidate:
    """A candidate that passes every gate, so each test changes one thing."""
    defaults = dict(
        page_type="flight",
        key="AA/100/BOS-LGA",
        ops_t12=300,
        last_seen=PERIOD_END,
        data_period_end=PERIOD_END,
        summary_rules_matched=3,
        max_sibling_similarity=0.4,
    )
    return PageCandidate(**{**defaults, **kw})


def decide(**kw):
    return evaluate(candidate(**kw), today=TODAY)


# --- baseline --------------------------------------------------------------


def test_a_healthy_page_publishes():
    d = decide()
    assert d.outcome is Outcome.PUBLISH
    assert d.reasons == ["passed all gates"]


def test_unknown_page_type_is_rejected():
    with pytest.raises(ValueError, match="Unknown page type"):
        evaluate(candidate(page_type="wormhole"), today=TODAY)


# --- flight volume thresholds: >=30 publish, 10-29 noindex, <10 drop -------


@pytest.mark.parametrize("ops", [30, 31, 5000])
def test_flight_publishes_at_or_above_thirty(ops):
    assert decide(ops_t12=ops).outcome is Outcome.PUBLISH


@pytest.mark.parametrize("ops", [10, 20, 29])
def test_flight_noindexes_between_ten_and_twentynine(ops):
    d = decide(ops_t12=ops)
    assert d.outcome is Outcome.NOINDEX
    assert "trailing 12 months" in d.reasons[0]


@pytest.mark.parametrize("ops", [0, 9])
def test_flight_drops_below_ten(ops):
    assert decide(ops_t12=ops).outcome is Outcome.DROP


# --- other page types ------------------------------------------------------


def test_route_publishes_at_sixty_and_drops_below():
    assert decide(page_type="route", key="BOS-LGA", ops_t12=60).outcome is Outcome.PUBLISH
    assert decide(page_type="route", key="BOS-LGA", ops_t12=59).outcome is Outcome.DROP


def test_airport_noindexes_rather_than_drops():
    """A quiet airport still deserves a page, just not an indexed one."""
    assert decide(page_type="airport", key="HYA", ops_t12=499).outcome is Outcome.NOINDEX
    assert decide(page_type="airport", key="BOS", ops_t12=500).outcome is Outcome.PUBLISH


def test_airline_publishes_for_reporting_carriers_at_any_volume():
    assert (
        decide(page_type="airline", key="AA", ops_t12=1, is_reporting_carrier=True).outcome
        is Outcome.PUBLISH
    )
    assert decide(page_type="airline", key="ZZ", ops_t12=99999).outcome is Outcome.DROP


def test_monthly_list_inherits_its_airport_page():
    published = decide(page_type="monthly_list", key="BOS/2026-01", parent_outcome=Outcome.PUBLISH)
    assert published.outcome is Outcome.PUBLISH
    for parent in (Outcome.NOINDEX, Outcome.DROP, None):
        d = decide(page_type="monthly_list", key="BOS/2026-01", parent_outcome=parent)
        assert d.outcome is Outcome.DROP


# --- stale flights ---------------------------------------------------------


def test_stale_flight_is_noindexed_and_points_at_its_route():
    d = decide(last_seen=date(2025, 7, 1))  # 214 days before the period end
    assert d.outcome is Outcome.NOINDEX
    assert d.redirect_hint == "route"
    assert "not seen for 214 days" in " ".join(d.reasons)


def test_staleness_boundary_is_exactly_180_days():
    """The cutoff is measured against the data period end, not against TODAY."""
    assert (PERIOD_END - date(2025, 8, 4)).days == 180
    assert decide(last_seen=date(2025, 8, 4)).outcome is Outcome.NOINDEX
    assert decide(last_seen=date(2025, 8, 5)).outcome is Outcome.PUBLISH  # 179 days


def test_stale_cutoff_helper_matches_the_rule():
    assert stale_cutoff(date(2026, 1, 31)) == date(2025, 8, 4)


def test_staleness_only_applies_to_flights():
    d = decide(page_type="route", key="BOS-LGA", last_seen=date(2020, 1, 1))
    assert d.redirect_hint is None


# --- universal gates -------------------------------------------------------


def test_missing_required_blocks_drops_the_page():
    d = decide(missing_blocks=("delay_causes", "monthly_chart"))
    assert d.outcome is Outcome.DROP
    assert "delay_causes, monthly_chart" in " ".join(d.reasons)


def test_no_matched_summary_rule_drops_the_page():
    d = decide(summary_rules_matched=0)
    assert d.outcome is Outcome.DROP
    assert "no summary rule matched" in d.reasons


def test_too_similar_to_a_sibling_is_noindexed():
    assert decide(max_sibling_similarity=0.91).outcome is Outcome.NOINDEX
    assert decide(max_sibling_similarity=0.90).outcome is Outcome.PUBLISH


def test_uncomputed_gates_are_recorded_as_skipped_not_silently_passed():
    """The summary and similarity gates arrive in M6. Until then they must be
    visible in the report rather than quietly absent."""
    d = decide(max_sibling_similarity=None, summary_rules_matched=None)
    assert d.outcome is Outcome.PUBLISH
    assert any("similarity" in s for s in d.skipped)
    assert any("summary" in s for s in d.skipped)
    assert report_rows({"x": d})[0]["skipped_gates"].count("(") == 2


def test_stale_data_noindexes_every_page():
    d = evaluate(candidate(), today=date(2026, 6, 1))  # 121 days after the period
    assert d.outcome is Outcome.NOINDEX
    assert "data is 121 days old" in " ".join(d.reasons)


def test_normal_bts_lag_is_not_treated_as_stale():
    """A month published six weeks late is ordinary, not a failure."""
    assert evaluate(candidate(), today=date(2026, 3, 15)).outcome is Outcome.PUBLISH


def test_missing_data_period_is_a_drop_not_a_pass():
    d = evaluate(candidate(data_period_end=None), today=TODAY)
    assert d.outcome is Outcome.DROP
    assert "no data period recorded" in d.reasons


# --- combination behaviour -------------------------------------------------


def test_strictest_outcome_wins_over_a_passing_gate():
    """Plenty of operations must not rescue a page with no summary."""
    d = decide(ops_t12=10_000, summary_rules_matched=0)
    assert d.outcome is Outcome.DROP


def test_every_failing_reason_is_recorded():
    d = decide(ops_t12=12, summary_rules_matched=0, max_sibling_similarity=0.99)
    assert d.outcome is Outcome.DROP
    joined = " ".join(d.reasons)
    assert "trailing 12 months" in joined
    assert "no summary rule matched" in joined
    assert "similarity" in joined
    assert len(d.reasons) == 3


def test_thresholds_are_overridable_without_editing_rules():
    strict = Thresholds(flight_publish=500, flight_noindex=100)
    assert (
        evaluate(candidate(ops_t12=300), thresholds=strict, today=TODAY).outcome is Outcome.NOINDEX
    )


# --- reporting -------------------------------------------------------------


def test_report_and_summary():
    decisions = {
        "a": decide(),
        "b": decide(ops_t12=12),
        "c": decide(ops_t12=1),
    }
    assert summarize(decisions) == {"publish": 1, "noindex": 1, "drop": 1}
    rows = report_rows(decisions)
    assert [r["key"] for r in rows] == ["a", "b", "c"]
    assert rows[0]["outcome"] == "publish"
    assert "trailing 12 months" in rows[1]["reasons"]
