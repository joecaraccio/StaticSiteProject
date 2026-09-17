"""The quality gate runner.

Every generated page passes through here and comes out `publish`, `noindex` or
`drop` (CLAUDE.md: "Quality gates are not optional").

Two properties matter:

* **The strictest outcome wins.** A page with enough operations but no matched
  summary rule is still held back; passing one gate never overrides a failure.
* **Every reason is recorded, not just the first.** The CSV report is how you
  tell "12,000 dropped" from "12,000 dropped for these four reasons", which is
  what you need when tuning thresholds.

Thresholds come from docs/PLAN.md section 7 and live in one place, so changing
one is a single edit plus a DECISIONS.md entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum


class Outcome(Enum):
    """Ordered from most to least permissive; comparison picks the strictest."""

    PUBLISH = "publish"
    NOINDEX = "noindex"
    DROP = "drop"

    @property
    def severity(self) -> int:
        return {"publish": 0, "noindex": 1, "drop": 2}[self.value]

    def strictest(self, other: Outcome) -> Outcome:
        return self if self.severity >= other.severity else other


@dataclass(frozen=True)
class Thresholds:
    """Minimum trailing-12-month operations per page type, from PLAN.md §7."""

    flight_publish: int = 30
    flight_noindex: int = 10
    route_publish: int = 60
    airport_publish: int = 500
    #: A flight not seen for this long is noindexed and points at its route page.
    stale_flight_days: int = 180
    #: Text similarity to sibling pages above this is too thin to index.
    max_sibling_similarity: float = 0.90
    #: How stale the underlying data may be before pages are held back. BTS
    #: publishes a month a few weeks after it closes, so this allows two months
    #: plus slack rather than treating normal lag as a failure.
    max_data_age_days: int = 100


THRESHOLDS = Thresholds()


@dataclass(frozen=True)
class PageCandidate:
    """Everything the gates need to judge one page.

    Deliberately a plain value object: the gate rules must be testable without a
    database, and they must not be able to reach back for more data mid-decision.
    """

    page_type: str
    key: str
    ops_t12: int
    #: Latest flight date in the data for this entity.
    last_seen: date | None = None
    #: Latest flight date across the whole dataset; "stale" and "data age" are
    #: measured against this, not against today, matching the trailing-12 rule.
    data_period_end: date | None = None
    #: Blocks the template requires that came back without real data.
    missing_blocks: tuple[str, ...] = ()
    #: How many summary rules matched. Zero means the engine ran and found
    #: nothing to say, which is a drop. None means the engine has not run yet
    #: (the rule engine lands in M6), which is recorded as a skipped gate rather
    #: than silently passing.
    summary_rules_matched: int | None = None
    #: Highest similarity to a sibling page, when computed (M6). None = not yet.
    max_sibling_similarity: float | None = None
    #: Airline pages exist for reporting carriers regardless of volume.
    is_reporting_carrier: bool = False
    #: Monthly list pages inherit their airport page's outcome.
    parent_outcome: Outcome | None = None


@dataclass
class Decision:
    outcome: Outcome
    reasons: list[str] = field(default_factory=list)
    #: Set when a noindexed page should point somewhere better.
    redirect_hint: str | None = None
    #: Gates that could not run because their input has not been computed yet.
    #: Surfaced in the report so an unenforced gate is visible, not invisible.
    skipped: list[str] = field(default_factory=list)

    def apply(self, outcome: Outcome, reason: str) -> None:
        """Fold in one rule's verdict, keeping the strictest so far."""
        self.outcome = self.outcome.strictest(outcome)
        self.reasons.append(reason)

    def skip(self, gate: str, why: str) -> None:
        self.skipped.append(f"{gate} ({why})")


# --- per-page-type volume rules -------------------------------------------


def _flight_volume(c: PageCandidate, d: Decision, t: Thresholds) -> None:
    if c.ops_t12 >= t.flight_publish:
        return
    if c.ops_t12 >= t.flight_noindex:
        d.apply(
            Outcome.NOINDEX,
            f"only {c.ops_t12} operations in trailing 12 months (<{t.flight_publish})",
        )
    else:
        d.apply(
            Outcome.DROP, f"only {c.ops_t12} operations in trailing 12 months (<{t.flight_noindex})"
        )


def _route_volume(c: PageCandidate, d: Decision, t: Thresholds) -> None:
    if c.ops_t12 < t.route_publish:
        d.apply(
            Outcome.DROP, f"only {c.ops_t12} operations in trailing 12 months (<{t.route_publish})"
        )


def _airport_volume(c: PageCandidate, d: Decision, t: Thresholds) -> None:
    if c.ops_t12 < t.airport_publish:
        d.apply(
            Outcome.NOINDEX,
            f"only {c.ops_t12} operations in trailing 12 months (<{t.airport_publish})",
        )


def _airline_volume(c: PageCandidate, d: Decision, t: Thresholds) -> None:
    if not c.is_reporting_carrier:
        d.apply(Outcome.DROP, "not a reporting carrier")


def _monthly_list_volume(c: PageCandidate, d: Decision, t: Thresholds) -> None:
    if c.parent_outcome is None:
        d.apply(Outcome.DROP, "no airport page outcome to inherit")
    elif c.parent_outcome is not Outcome.PUBLISH:
        d.apply(Outcome.DROP, f"airport page is {c.parent_outcome.value}, not published")


VOLUME_RULES = {
    "flight": _flight_volume,
    "route": _route_volume,
    "airport": _airport_volume,
    "airline": _airline_volume,
    "monthly_list": _monthly_list_volume,
}


# --- rules that apply to every page ---------------------------------------


def _stale_entity(c: PageCandidate, d: Decision, t: Thresholds) -> None:
    """A flight that stopped operating should not look current."""
    if c.page_type != "flight" or c.last_seen is None or c.data_period_end is None:
        return
    gap = (c.data_period_end - c.last_seen).days
    if gap >= t.stale_flight_days:
        d.apply(Outcome.NOINDEX, f"not seen for {gap} days (>={t.stale_flight_days})")
        if d.redirect_hint is None:
            d.redirect_hint = "route"


def _required_blocks(c: PageCandidate, d: Decision, t: Thresholds) -> None:
    if c.missing_blocks:
        d.apply(Outcome.DROP, f"required blocks without data: {', '.join(c.missing_blocks)}")


def _summary_rules(c: PageCandidate, d: Decision, t: Thresholds) -> None:
    if c.summary_rules_matched is None:
        d.skip("summary", "rule engine not run; arrives in M6")
        return
    if c.summary_rules_matched < 1:
        d.apply(Outcome.DROP, "no summary rule matched")


def _similarity(c: PageCandidate, d: Decision, t: Thresholds) -> None:
    if c.max_sibling_similarity is None:
        d.skip("similarity", "not computed; arrives in M6")
        return
    if c.max_sibling_similarity > t.max_sibling_similarity:
        d.apply(
            Outcome.NOINDEX,
            f"text similarity to a sibling page is {c.max_sibling_similarity:.2f} "
            f"(>{t.max_sibling_similarity})",
        )


def _data_age(c: PageCandidate, d: Decision, t: Thresholds, today: date | None = None) -> None:
    if c.data_period_end is None:
        d.apply(Outcome.DROP, "no data period recorded")
        return
    age = ((today or date.today()) - c.data_period_end).days
    if age > t.max_data_age_days:
        d.apply(Outcome.NOINDEX, f"data is {age} days old (>{t.max_data_age_days})")


UNIVERSAL_RULES = (_stale_entity, _required_blocks, _summary_rules, _similarity)


def evaluate(
    candidate: PageCandidate,
    *,
    thresholds: Thresholds = THRESHOLDS,
    today: date | None = None,
) -> Decision:
    """Run every gate and return the strictest outcome with all reasons."""
    if candidate.page_type not in VOLUME_RULES:
        raise ValueError(
            f"Unknown page type {candidate.page_type!r}; expected one of "
            f"{', '.join(sorted(VOLUME_RULES))}"
        )

    decision = Decision(outcome=Outcome.PUBLISH)
    VOLUME_RULES[candidate.page_type](candidate, decision, thresholds)
    for rule in UNIVERSAL_RULES:
        rule(candidate, decision, thresholds)
    _data_age(candidate, decision, thresholds, today=today)

    if not decision.reasons:
        decision.reasons.append("passed all gates")
    return decision


def report_rows(decisions: dict[str, Decision]) -> list[dict[str, str]]:
    """Flatten decisions into CSV-ready rows: one row per page, reasons joined."""
    return [
        {
            "key": key,
            "outcome": d.outcome.value,
            "redirect_hint": d.redirect_hint or "",
            "reasons": "; ".join(d.reasons),
            "skipped_gates": "; ".join(d.skipped),
        }
        for key, d in sorted(decisions.items())
    ]


def summarize(decisions: dict[str, Decision]) -> dict[str, int]:
    counts = dict.fromkeys((o.value for o in Outcome), 0)
    for d in decisions.values():
        counts[d.outcome.value] += 1
    return counts


def stale_cutoff(data_period_end: date, thresholds: Thresholds = THRESHOLDS) -> date:
    """The last_seen date at which a flight becomes stale. Useful in SQL filters."""
    return data_period_end - timedelta(days=thresholds.stale_flight_days)
