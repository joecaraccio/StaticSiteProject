"""Summary rules: deterministic sentences from metrics the pipeline already computed."""

from __future__ import annotations

import pytest

from pipeline.summaries.rules import SummaryContext, summarize


def ctx(**kw) -> SummaryContext:
    defaults = dict(
        page_type="flight",
        subject="AA 100",
        ops_scheduled=1000,
        ops_measurable=980,
        on_time_rate=0.82,
        cancellation_rate=0.015,
        avg_arr_delay_when_late_min=47.4,
        share_3h_plus=0.012,
    )
    return SummaryContext(**{**defaults, **kw})


def text(**kw) -> str:
    return " ".join(summarize(ctx(**kw)).sentences)


# --- determinism -----------------------------------------------------------


def test_the_same_input_always_produces_the_same_words():
    assert summarize(ctx()).sentences == summarize(ctx()).sentences


def test_matched_rule_names_are_reported():
    result = summarize(ctx())
    assert result.matched_rules[0] == "headline"
    assert len(result) == len(result.sentences)


def test_sentences_follow_the_declared_rule_order():
    result = summarize(ctx(peer_rate=0.70, peer_label="this route"))
    assert result.matched_rules.index("headline") < result.matched_rules.index("versus_peers")
    assert result.matched_rules[-1] != "headline"


# --- headline bands --------------------------------------------------------


@pytest.mark.parametrize(
    "rate,phrase",
    [
        (0.92, "is usually on time"),
        (0.85, "is usually on time"),
        (0.78, "is on time more often than not"),
        (0.64, "runs late often enough to plan around"),
        (0.41, "is usually late"),
    ],
)
def test_headline_band_wording(rate, phrase):
    assert phrase in text(on_time_rate=rate)


def test_headline_reports_the_denominator_it_used():
    assert "across 980 flights that operated" in text()


def test_no_headline_without_a_rate():
    """A page with nothing measurable must produce no sentence, not a hedge."""
    result = summarize(ctx(on_time_rate=None, ops_measurable=0))
    assert "headline" not in result.matched_rules


# --- comparison ------------------------------------------------------------


def test_comparison_against_peers_gives_direction_and_size():
    assert "9 points better than the BOS to LGA route" in text(
        on_time_rate=0.82, peer_rate=0.73, peer_label="the BOS to LGA route"
    )
    assert "9 points worse than" in text(
        on_time_rate=0.64, peer_rate=0.73, peer_label="the BOS to LGA route"
    )


def test_a_small_gap_is_called_average_not_a_difference():
    assert "about average" in text(on_time_rate=0.74, peer_rate=0.73, peer_label="this route")


def test_better_option_is_only_mentioned_when_meaningfully_better():
    assert "DL 200 is the most reliable option" in text(
        on_time_rate=0.70, best_alternative=("DL 200", 0.91)
    )
    assert "most reliable option" not in text(on_time_rate=0.90, best_alternative=("DL 200", 0.91))


# --- seasonality -----------------------------------------------------------


def test_worst_month_needs_enough_months_to_be_a_pattern():
    months = (*((f"2025-{m:02d}", 0.85) for m in range(1, 6)), ("2025-06", 0.55))
    assert "worst month" not in text(monthly=months[:5])
    assert "June 2025" in text(monthly=months)


def test_a_flat_year_produces_no_worst_month_claim():
    months = tuple((f"2025-{m:02d}", 0.82) for m in range(1, 13))
    assert "worst month" not in text(monthly=months)


# --- cancellations ---------------------------------------------------------


def test_zero_cancellations_is_stated_plainly():
    assert "No flights were cancelled" in text(cancellation_rate=0.0)


def test_rare_cancellations_avoid_a_silly_one_in_n():
    assert "Cancellations are rare, at 0.4%" in text(cancellation_rate=0.004)


def test_common_cancellations_get_a_one_in_n():
    assert "roughly one in 40" in text(cancellation_rate=0.025)


# --- severity and caveats --------------------------------------------------


def test_how_late_when_late():
    assert "47 minutes behind schedule" in text()


def test_severe_delays_below_one_percent_are_not_worth_a_sentence():
    assert "three or more hours" not in text(share_3h_plus=0.009)
    assert "1.2% of flights arrived three or more hours late" in text(share_3h_plus=0.012)


def test_small_samples_are_caveated_last():
    result = summarize(ctx(ops_scheduled=34, ops_measurable=33))
    assert result.matched_rules[-1] == "small_sample"
    assert "only 34 flights" in result.sentences[-1]


def test_large_samples_get_no_caveat():
    assert "indicative" not in text(ops_scheduled=1000)


# --- nothing to say --------------------------------------------------------


def test_an_empty_page_matches_no_rules_so_the_gate_can_drop_it():
    empty = SummaryContext(
        page_type="flight",
        subject="AA 1",
        ops_scheduled=0,
        ops_measurable=0,
        on_time_rate=None,
        cancellation_rate=None,
        avg_arr_delay_when_late_min=None,
        share_3h_plus=None,
    )
    assert len(summarize(empty)) == 0
