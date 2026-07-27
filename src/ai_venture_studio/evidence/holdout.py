"""Holdout tooling (§22.63.3) — holdouts are cheap; default to them.

Withhold the channel from a random 10-20% of the addressable set (or
stagger by region) and compare: usually the difference between a decision
and a guess, and for organic channels nearly free. Assignment is
deterministic content-addressed hashing — reproducible from the salt, no
runtime randomness, so the assignment itself is auditable.

Unit ids live inside the analytics boundary; what leaves is the aggregate
comparison, typed by attribution_typer as the only causal-eligible
observation in the system.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel

from ai_venture_studio.evidence.attribution import TypedObservation, type_observation
from ai_venture_studio.evidence.cohort import wilson_interval


class HoldoutAssignment(BaseModel):
    exposed: list[str]
    holdout: list[str]
    method: str  # random | geo
    salt: str
    holdout_fraction: float


class HoldoutComparison(BaseModel):
    exposed_n: int
    exposed_rate: float
    holdout_n: int
    holdout_rate: float
    lift: float
    exposed_ci: tuple[float, float]
    holdout_ci: tuple[float, float]
    typed: TypedObservation
    conclusive: bool
    detail: str


def assign_holdout(
    unit_ids: list[str], *, holdout_fraction: float = 0.15, salt: str
) -> HoldoutAssignment:
    """Random split by salted hash — stable for a given salt, so re-running
    the analysis reproduces the assignment exactly."""
    if not 0 < holdout_fraction < 1:
        raise ValueError("holdout_fraction must be in (0, 1)")
    if not salt:
        raise ValueError("salt is required — an unsalted split is not auditable")
    exposed, holdout = [], []
    threshold = int(holdout_fraction * 2**32)
    for unit in unit_ids:
        digest = hashlib.sha256(f"{salt}:{unit}".encode()).digest()
        bucket = int.from_bytes(digest[:4], "big")
        (holdout if bucket < threshold else exposed).append(unit)
    return HoldoutAssignment(
        exposed=exposed,
        holdout=holdout,
        method="random",
        salt=salt,
        holdout_fraction=holdout_fraction,
    )


def assign_geo_holdout(
    units_by_region: dict[str, list[str]], holdout_regions: list[str]
) -> HoldoutAssignment:
    exposed, holdout = [], []
    for region, units in sorted(units_by_region.items()):
        (holdout if region in holdout_regions else exposed).extend(units)
    total = len(exposed) + len(holdout)
    return HoldoutAssignment(
        exposed=exposed,
        holdout=holdout,
        method="geo",
        salt=",".join(sorted(holdout_regions)),
        holdout_fraction=len(holdout) / total if total else 0.0,
    )


class ExposureLog:
    """Append-only record of who was actually exposed to which arm — the
    analysis compares what happened, not what was planned."""

    def __init__(self) -> None:
        self._records: list[tuple[str, str, str]] = []

    def log(self, unit: str, arm: str, at: str) -> None:
        self._records.append((unit, arm, at))

    def units(self, arm: str) -> set[str]:
        return {unit for unit, a, _ in self._records if a == arm}

    def __len__(self) -> int:
        return len(self._records)


def compare_holdout(
    *,
    exposed_hits: int,
    exposed_n: int,
    holdout_hits: int,
    holdout_n: int,
    method: str = "holdout_experiment",
) -> HoldoutComparison:
    """The aggregate comparison that leaves the boundary. Conclusive only
    when the intervals separate — overlapping intervals are reported as
    exactly that, not narrated into a win."""
    if exposed_n == 0 or holdout_n == 0:
        raise ValueError("both arms need units — an empty arm is not a holdout")
    exposed_rate = exposed_hits / exposed_n
    holdout_rate = holdout_hits / holdout_n
    exposed_ci = wilson_interval(exposed_hits, exposed_n)
    holdout_ci = wilson_interval(holdout_hits, holdout_n)
    separated = exposed_ci[0] > holdout_ci[1] or holdout_ci[0] > exposed_ci[1]
    return HoldoutComparison(
        exposed_n=exposed_n,
        exposed_rate=exposed_rate,
        holdout_n=holdout_n,
        holdout_rate=holdout_rate,
        lift=exposed_rate - holdout_rate,
        exposed_ci=exposed_ci,
        holdout_ci=holdout_ci,
        typed=type_observation(method),
        conclusive=separated,
        detail=(
            "intervals separate; the lift may ground a causal claim"
            if separated
            else "intervals overlap — inconclusive, and inconclusive enters "
            "nothing (ADR-U24)"
        ),
    )
