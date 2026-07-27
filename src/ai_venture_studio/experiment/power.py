"""power_calc (§21.61.3) — underpowered tests are not run.

If the required n is unreachable within the window given current traffic,
the honest output is BLOCKED(INSUFFICIENT_POWER) with the required n
stated, and the correct next action is usually a qualitative test rather
than a smaller quantitative one. For a small team's traffic this is the
COMMON case, and pretending otherwise is how the outer loop starts lying
to itself.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from ai_venture_studio.evidence.cohort import required_n_two_proportions


class PowerResult(BaseModel):
    status: str  # ok | BLOCKED(INSUFFICIENT_POWER)
    n_per_arm: int
    total_n: int
    expected_days: int
    detail: str


def power_calc(
    *,
    baseline: float,
    mde_relative: float,
    arms: int,
    weekly_traffic: int,
    max_days: int,
    alpha: float = 0.05,
    power: float = 0.80,
) -> PowerResult:
    n_per_arm = required_n_two_proportions(
        baseline, mde_relative, alpha=alpha, power=power
    )
    total = n_per_arm * arms
    if weekly_traffic <= 0:
        expected_days = math.inf
    else:
        expected_days = math.ceil(total / weekly_traffic * 7)
    if expected_days > max_days:
        return PowerResult(
            status="BLOCKED(INSUFFICIENT_POWER)",
            n_per_arm=n_per_arm,
            total_n=total,
            expected_days=int(min(expected_days, 10**6)),
            detail=f"needs n={n_per_arm}/arm ({total} total) ≈ "
            f"{int(min(expected_days, 10**6))} days at {weekly_traffic}/week, over "
            f"the {max_days}-day window — do not run a smaller version; run a "
            "qualitative test or grow traffic first (§21.61.3)",
        )
    return PowerResult(
        status="ok",
        n_per_arm=n_per_arm,
        total_n=total,
        expected_days=int(expected_days),
        detail=f"n={n_per_arm}/arm reachable in ~{int(expected_days)} days",
    )
