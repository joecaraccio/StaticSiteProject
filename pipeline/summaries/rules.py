"""Rule-based page summaries.

CLAUDE.md: "Summary text is rule-based. Page summaries come from deterministic,
tested rules in `pipeline/summaries/`, not from a language model at build time."

Each rule is a function over a `SummaryContext` that returns one sentence, or
None when it has nothing to say. The page shows the sentences that matched, in a
fixed order, so two pages with similar numbers read similarly and the same inputs
always produce the same words.

Rules never compute statistics — they only phrase what the metrics layer already
produced. That keeps a number from being defined in two places.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SummaryContext:
    """Everything the rules may look at. Nothing else is in scope."""

    page_type: str
    #: How the subject is named in a sentence, e.g. "AA 100" or "the BOS to LGA route".
    subject: str
    ops_scheduled: int
    ops_measurable: int
    on_time_rate: float | None = None
    cancellation_rate: float | None = None
    avg_arr_delay_when_late_min: float | None = None
    share_3h_plus: float | None = None
    #: (month label, on-time rate) for months with a rate, oldest first.
    monthly: tuple[tuple[str, float], ...] = ()
    #: The comparable group's rate, e.g. the route average on a flight page.
    peer_rate: float | None = None
    peer_label: str | None = None
    #: The best alternative on the same route, if it is not this page.
    best_alternative: tuple[str, float] | None = None


#: Below this many operations, figures are shown with a caveat.
SMALL_SAMPLE = 60
#: A difference smaller than this is noise, not a finding.
MEANINGFUL_GAP = 0.03


def _pct(value: float, digits: int = 0) -> str:
    return f"{value * 100:.{digits}f}%"


def _points(a: float, b: float) -> int:
    return round(abs(a - b) * 100)


def _month_name(label: str) -> str:
    year, month = label.split("-")
    names = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    return f"{names[int(month) - 1]} {year}"


# --- the rules -------------------------------------------------------------


def headline(c: SummaryContext) -> str | None:
    """Always first: the number someone came for, in words."""
    if c.on_time_rate is None or c.ops_measurable == 0:
        return None
    rate = c.on_time_rate
    if rate >= 0.85:
        verdict = "is usually on time"
    elif rate >= 0.75:
        verdict = "is on time more often than not"
    elif rate >= 0.60:
        verdict = "runs late often enough to plan around"
    else:
        verdict = "is usually late"
    return (
        f"{c.subject} {verdict}: {_pct(rate)} of flights arrived within 15 minutes "
        f"of schedule, across {c.ops_measurable:,} flights that operated."
    )


def versus_peers(c: SummaryContext) -> str | None:
    """Context beats a bare percentage: 78% is good on one route, poor on another."""
    if c.on_time_rate is None or c.peer_rate is None or c.peer_label is None:
        return None
    gap = c.on_time_rate - c.peer_rate
    if abs(gap) < MEANINGFUL_GAP:
        return f"That is about average for {c.peer_label} ({_pct(c.peer_rate)})."
    direction = "better" if gap > 0 else "worse"
    return (
        f"That is {_points(c.on_time_rate, c.peer_rate)} points {direction} than "
        f"{c.peer_label}, which averages {_pct(c.peer_rate)}."
    )


def better_option(c: SummaryContext) -> str | None:
    """The whole point of the site: is there a better flight?"""
    if c.best_alternative is None or c.on_time_rate is None:
        return None
    name, rate = c.best_alternative
    if rate - c.on_time_rate < MEANINGFUL_GAP:
        return None
    return (
        f"{name} is the most reliable option on this route at {_pct(rate)}, "
        f"{_points(rate, c.on_time_rate)} points better."
    )


def worst_month(c: SummaryContext) -> str | None:
    """Seasonality is actionable: it tells someone when not to fly."""
    if len(c.monthly) < 6:
        return None
    label, rate = min(c.monthly, key=lambda m: m[1])
    if c.on_time_rate is None or c.on_time_rate - rate < MEANINGFUL_GAP * 2:
        return None
    return f"The worst month in the period was {_month_name(label)}, at {_pct(rate)} on time."


def cancellations(c: SummaryContext) -> str | None:
    if c.cancellation_rate is None or c.ops_scheduled == 0:
        return None
    rate = c.cancellation_rate
    if rate == 0:
        return "No flights were cancelled in this period."
    if rate < 0.01:
        return f"Cancellations are rare, at {_pct(rate, 1)} of scheduled flights."
    one_in = round(1 / rate)
    return f"{_pct(rate, 1)} of scheduled flights were cancelled — roughly one in {one_in:,}."


def how_late(c: SummaryContext) -> str | None:
    if c.avg_arr_delay_when_late_min is None:
        return None
    minutes = round(c.avg_arr_delay_when_late_min)
    return f"When it does arrive late, it is {minutes} minutes behind schedule on average."


def severe_delays(c: SummaryContext) -> str | None:
    """A 3-hour delay is a different category of problem from a 20-minute one."""
    if c.share_3h_plus is None or c.share_3h_plus < 0.01:
        return None
    return f"{_pct(c.share_3h_plus, 1)} of flights arrived three or more hours late."


def small_sample(c: SummaryContext) -> str | None:
    """Last, so the caveat lands after the figures it qualifies.

    A caveat with nothing to qualify is not a summary. Without it this rule would
    match on an empty page and let the gate pass a page whose only sentence is a
    warning about its own emptiness.
    """
    if c.ops_scheduled == 0 or c.on_time_rate is None:
        return None
    if c.ops_scheduled >= SMALL_SAMPLE:
        return None
    return (
        f"This is based on only {c.ops_scheduled:,} flights, so treat these figures as "
        "indicative rather than settled."
    )


#: Order matters: this is the order the sentences appear on the page.
RULES: tuple[Callable[[SummaryContext], str | None], ...] = (
    headline,
    versus_peers,
    better_option,
    worst_month,
    cancellations,
    how_late,
    severe_delays,
    small_sample,
)


@dataclass
class Summary:
    sentences: list[str] = field(default_factory=list)
    matched_rules: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.sentences)


def summarize(context: SummaryContext) -> Summary:
    """Run every rule in order and collect the sentences that matched."""
    summary = Summary()
    for rule in RULES:
        sentence = rule(context)
        if sentence:
            summary.sentences.append(sentence)
            summary.matched_rules.append(rule.__name__)
    return summary
