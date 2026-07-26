"""cohort_calc and sample_sufficiency_check (§22.62.2).

Cohort readings are time-boxed and carry n and an interval; a reading on
an incomplete window is marked so (Cohort-Validity's named catch: a 30-day
retention number read on day 11). sample_sufficiency_check gives
`insufficient_evidence` real teeth: a verdict on n=6 is not a verdict, and
"we don't know yet, here's what it would take to know" is a SUCCESSFUL P4
output — the required n is stated, not lamented.

Statistics are stdlib (NormalDist): Wilson interval for readings, a
two-proportion normal-approximation power calculation for sufficiency. The
heavier machinery (sequential boundaries, BH correction) belongs to the
experiment MAS milestone, not here.
"""

from __future__ import annotations

import datetime as dt
import math
from statistics import NormalDist

from pydantic import BaseModel

from autoproduct.evidence.analytics import AnalyticsStore
from autoproduct.evidence.metrics import MetricDefinition

_NORMAL = NormalDist()


class CohortReading(BaseModel):
    metric_id: str
    cohort: dict[str, str]
    n: int
    numerator: int
    value: float
    ci_low: float
    ci_high: float
    window_complete: bool
    source_type: str = "primary_measured"  # our analytics — the only causal type


class SufficiencyVerdict(BaseModel):
    sufficient: bool
    n: int
    required_n: int
    message: str


def wilson_interval(hits: int, n: int, *, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    z = _NORMAL.inv_cdf(1 - alpha / 2)
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def cohort_calc(
    store: AnalyticsStore,
    metric: MetricDefinition,
    *,
    cohort_field: str,
    cohort_start: dt.date,
    today: dt.date,
) -> list[CohortReading]:
    """Read one metric per cohort through the analytics boundary — the
    reading inherits the boundary's floor and refusals by construction."""
    window_complete = (
        cohort_start + dt.timedelta(days=metric.window_days or 0) <= today
    )
    readings = []
    for agg in store.cohort_aggregate(
        group_by=[cohort_field], numerator_event=metric.numerator_event
    ):
        low, high = wilson_interval(agg.numerator, agg.n)
        readings.append(
            CohortReading(
                metric_id=metric.id,
                cohort=agg.group,
                n=agg.n,
                numerator=agg.numerator,
                value=agg.value,
                ci_low=low,
                ci_high=high,
                window_complete=window_complete,
            )
        )
    return readings


def sample_sufficiency_check(
    *,
    n: int,
    baseline: float,
    mde_relative: float,
    alpha: float = 0.05,
    power: float = 0.80,
) -> SufficiencyVerdict:
    """Can n support a verdict on the stated effect size?

    Two-proportion normal approximation, per group. The honest output for
    a small product is frequently `sufficient: false` with the required n
    stated (§22.62.2) — the same posture as BLOCKED(INSUFFICIENT_POWER).
    """
    if not 0 < baseline < 1 or mde_relative <= 0:
        raise ValueError("baseline must be in (0,1) and mde_relative positive")
    p2 = min(baseline * (1 + mde_relative), 0.999)
    z_alpha = _NORMAL.inv_cdf(1 - alpha / 2)
    z_beta = _NORMAL.inv_cdf(power)
    variance = baseline * (1 - baseline) + p2 * (1 - p2)
    required = math.ceil(((z_alpha + z_beta) ** 2 * variance) / (p2 - baseline) ** 2)
    sufficient = n >= required
    return SufficiencyVerdict(
        sufficient=sufficient,
        n=n,
        required_n=required,
        message=(
            f"n={n} supports the {mde_relative:.0%} relative effect at "
            f"alpha={alpha}, power={power}"
            if sufficient
            else f"insufficient_evidence: n={n} < required n={required} for a "
            f"{mde_relative:.0%} relative effect — a verdict here is not a verdict"
        ),
    )
