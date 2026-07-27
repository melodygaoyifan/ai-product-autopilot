"""Sequential monitoring (§21.61.3) — peek safely or not at all.

Continuous operation means the agent WILL look at accumulating results;
peeking without a sequential design invalidates fixed-horizon inference
(Johari et al., KDD 2017). The design here is the classic O'Brien-Fleming
group-sequential boundary for equally spaced looks — z_k = z_final·√(K/k)
— conservative early, near-nominal at the horizon, computable exactly
from the stdlib. Lan-DeMets flexible spending is the documented upgrade
path; what is non-negotiable is that the boundary is pre-specified and
"stop at the planned horizon or the boundary. No other stop is legal."
"""

from __future__ import annotations

import math
from statistics import NormalDist

from pydantic import BaseModel

_NORMAL = NormalDist()


class PeekVerdict(BaseModel):
    peek_index: int
    z_stat: float
    boundary: float
    action: str  # continue | stop_efficacy
    detail: str


class IllegalStopError(RuntimeError):
    """A stop outside the boundary or the horizon. Not a warning."""


def obrien_fleming_boundaries(peeks: int, *, alpha: float = 0.05) -> list[float]:
    """Per-peek two-sided z thresholds for K equally spaced looks."""
    if peeks < 1:
        raise ValueError("at least one look (the horizon) is required")
    z_final = _NORMAL.inv_cdf(1 - alpha / 2)
    return [z_final * math.sqrt(peeks / k) for k in range(1, peeks + 1)]


def peek(z_stat: float, peek_index: int, boundaries: list[float]) -> PeekVerdict:
    """Evaluate one pre-planned look. peek_index is 1-based."""
    if not 1 <= peek_index <= len(boundaries):
        raise IllegalStopError(
            f"look {peek_index} is not in the pre-registered schedule of "
            f"{len(boundaries)} — no other stop is legal"
        )
    boundary = boundaries[peek_index - 1]
    crossed = abs(z_stat) >= boundary
    return PeekVerdict(
        peek_index=peek_index,
        z_stat=z_stat,
        boundary=round(boundary, 4),
        action="stop_efficacy" if crossed else "continue",
        detail=(
            f"|z|={abs(z_stat):.3f} crossed the O'Brien-Fleming boundary "
            f"{boundary:.3f} at look {peek_index}/{len(boundaries)}"
            if crossed
            else f"|z|={abs(z_stat):.3f} under boundary {boundary:.3f} — continue "
            "to the next planned look; stopping here anyway would be p-hacking"
        ),
    )


def declare_stop(verdict: PeekVerdict) -> None:
    """The only legal stops: a crossed boundary, or the final planned look."""
    if verdict.action != "stop_efficacy":
        raise IllegalStopError(
            f"stop declared at look {verdict.peek_index} with "
            f"|z|={abs(verdict.z_stat):.3f} under the boundary "
            f"{verdict.boundary} — stop at the planned horizon or the "
            "sequential boundary; no other stop is legal (§21.61.2)"
        )
