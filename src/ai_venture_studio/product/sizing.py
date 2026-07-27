"""sizing_calc (§20.55.1) — the stage that refuses the top-down TAM.

Every size claim is bottom-up: named, individually-sourced factors, each
with its own source_type; a sensitivity range is MANDATORY on every factor
that is not primary_measured; the output is a range computed mechanically
from the sensitivities, never a point estimate. A factor nobody can source
is BLOCKED(MISSING_CONTEXT) naming the factor. A top-down figure may exist
only as a labeled third_party_report cross-check, and an unexplained
divergence is RECORDED, never reconciled by prose — the Sizing voter's job
is to catch smoothing.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ai_venture_studio.product.claims import SOURCE_TYPES


class SizingFactor(BaseModel):
    name: str
    value: float
    source_type: str = ""
    sensitivity: tuple[float, float] | None = None  # required unless primary_measured
    n: int | None = None


class TopDownCrosscheck(BaseModel):
    value: float
    source_type: str = "third_party_report"
    note: str = ""


class SizingIssue(BaseModel):
    factor: str = ""
    rule: str
    message: str


class SizingResult(BaseModel):
    status: str  # ok | blocked
    result_range: tuple[float, float] | None = None
    midpoint: float | None = None
    issues: list[SizingIssue] = Field(default_factory=list)
    divergence: dict = Field(default_factory=dict)


def sizing_calc(
    factors: list[SizingFactor],
    *,
    top_down_crosscheck: TopDownCrosscheck | None = None,
    divergence_ratio_flag: float = 3.0,
) -> SizingResult:
    issues: list[SizingIssue] = []
    if not factors:
        return SizingResult(
            status="blocked",
            issues=[SizingIssue(rule="no_factors", message="a size with no factors is a guess")],
        )

    for factor in factors:
        if factor.source_type not in SOURCE_TYPES:
            issues.append(
                SizingIssue(
                    factor=factor.name,
                    rule="unsourced_factor",
                    message=f"BLOCKED(MISSING_CONTEXT): factor {factor.name!r} has "
                    "no admissible source_type — name the source or drop the size",
                )
            )
            continue
        if factor.source_type != "primary_measured" and factor.sensitivity is None:
            issues.append(
                SizingIssue(
                    factor=factor.name,
                    rule="missing_sensitivity",
                    message=f"factor {factor.name!r} ({factor.source_type}) requires "
                    "a sensitivity range — unmeasured certainty is not certainty",
                )
            )
        if factor.sensitivity is not None:
            low, high = factor.sensitivity
            if not (low <= factor.value <= high) or low <= 0:
                issues.append(
                    SizingIssue(
                        factor=factor.name,
                        rule="bad_sensitivity",
                        message=f"sensitivity {factor.sensitivity} must be positive "
                        f"and bracket the value {factor.value}",
                    )
                )

    if any(i.rule in ("unsourced_factor", "bad_sensitivity") for i in issues) or any(
        i.rule == "missing_sensitivity" for i in issues
    ):
        return SizingResult(status="blocked", issues=issues)

    low = math.prod(
        (f.sensitivity[0] if f.sensitivity else f.value) for f in factors
    )
    high = math.prod(
        (f.sensitivity[1] if f.sensitivity else f.value) for f in factors
    )
    midpoint = math.prod(f.value for f in factors)

    divergence: dict = {}
    if top_down_crosscheck is not None:
        ratio = top_down_crosscheck.value / midpoint if midpoint else math.inf
        divergence = {
            "top_down": top_down_crosscheck.value,
            "bottom_up_midpoint": midpoint,
            "ratio": round(ratio, 2),
            "flagged": ratio >= divergence_ratio_flag or ratio <= 1 / divergence_ratio_flag,
            "note": "divergence recorded, not reconciled by narrative",
        }

    return SizingResult(
        status="ok",
        result_range=(low, high),
        midpoint=midpoint,
        issues=issues,
        divergence=divergence,
    )
