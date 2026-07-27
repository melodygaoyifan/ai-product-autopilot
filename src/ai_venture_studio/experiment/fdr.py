"""FDR control (§21.61.2, ADR-U24) — Benjamini-Hochberg for screening.

An agent that generates twenty variants is a false-discovery machine
unless the design stops it. Stage 1 screens k arms under BH; stage 2
validates the leader on a fresh sample. fdr_plan_check makes the plan
itself a gate: multi-arm screening without a declared correction fails
before any exposure.
"""

from __future__ import annotations

from pydantic import BaseModel

from ai_venture_studio.experiment.design import ExperimentDesign


class BHResult(BaseModel):
    index: int
    p_value: float
    threshold: float
    significant: bool


def benjamini_hochberg(p_values: list[float], q: float = 0.10) -> list[BHResult]:
    """Classic step-up BH: largest k with p_(k) <= (k/m)·q; all ranks up to
    k are discoveries. Returned in the input order."""
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    cutoff_rank = 0
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= rank / m * q:
            cutoff_rank = rank
    results: list[BHResult | None] = [None] * m
    for rank, idx in enumerate(order, start=1):
        results[idx] = BHResult(
            index=idx,
            p_value=p_values[idx],
            threshold=rank / m * q,
            significant=rank <= cutoff_rank,
        )
    return results  # type: ignore[return-value]


class FdrPlanIssue(BaseModel):
    rule: str
    message: str


def fdr_plan_check(design: ExperimentDesign) -> list[FdrPlanIssue]:
    issues = []
    stage1 = design.design_stage1
    if stage1.arms > 2 and stage1.correction != "benjamini_hochberg":
        issues.append(
            FdrPlanIssue(
                rule="no_screening_correction",
                message=f"{stage1.arms} screening arms with correction "
                f"{stage1.correction!r} — multi-arm screening requires BH (ADR-U24)",
            )
        )
    if not 0 < stage1.q <= 0.10:
        issues.append(
            FdrPlanIssue(
                rule="q_out_of_range",
                message=f"screening q={stage1.q} outside (0, 0.10] — the "
                "screening stage exists to be strict",
            )
        )
    if not design.design_stage2.fresh_sample:
        issues.append(
            FdrPlanIssue(
                rule="stale_validation_sample",
                message="stage 2 must validate on a FRESH sample — re-reading "
                "the screening sample is the false discovery it exists to stop",
            )
        )
    if design.monitoring.method == "sequential" and not design.monitoring.spending:
        issues.append(
            FdrPlanIssue(
                rule="no_spending_function",
                message="sequential monitoring requires a pre-specified "
                "spending function (§21.61.3)",
            )
        )
    return issues
