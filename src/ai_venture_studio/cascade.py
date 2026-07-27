"""Doc 16 §40 deterministic parts: voter cascades (ADR-U10), the serial
merge queue (§38.2 rule 2), and the GEPA budget schema (§40.1, ADR-U11).

Cascades: a cheap screening pass may run first, but anything it flags —
or cannot judge — escalates to the full panel, and the ESCALATED set must
satisfy the heterogeneity floor (distinct model families). The cascade
saves money on clean diffs; it never lowers the bar on dirty ones.

Merge queue: serial admission, feature lanes before sweep (sweep is
lowest priority by ADR-U37), bounded by ci_concurrency_max.

GEPA: the proposer's BUDGET is config the harness enforces; the proposer
itself (an LLM optimization loop) is a recorded open item — a budget
schema without a spender is safe; a spender without a budget is not.
"""

from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field

GEPA_FILE = "gepa.yaml"


class CascadePolicy(BaseModel):
    screening_enabled: bool = False  # off by default: full panel is the default
    critics_min_distinct_families: int = 2  # the heterogeneity floor
    escalate_on: tuple[str, ...] = ("finding", "blocked", "low_confidence")


class CascadeDecision(BaseModel):
    escalate: bool
    reason: str


def cascade_route(policy: CascadePolicy, *, screening_findings: int,
                  screening_blocked: bool) -> CascadeDecision:
    if not policy.screening_enabled:
        return CascadeDecision(escalate=True, reason="cascades off: full panel")
    if screening_blocked:
        return CascadeDecision(escalate=True, reason="screening could not judge")
    if screening_findings:
        return CascadeDecision(
            escalate=True,
            reason=f"{screening_findings} screening finding(s) — the cheap "
                   "pass saves money on clean diffs, never lowers the bar")
    return CascadeDecision(escalate=False, reason="screening clean")


def heterogeneity_ok(policy: CascadePolicy, model_families: list[str]) -> bool:
    """The escalated panel must span distinct families (§40.3) — a cascade
    that escalates into a monoculture kept the cost and lost the point."""
    return len(set(model_families)) >= policy.critics_min_distinct_families


class MergeQueueDecision(BaseModel):
    admit: list[str]
    deferred: list[str]
    reason: str


def merge_queue_admit(
    feature_prs: list[str], sweep_prs: list[str], *, ci_concurrency_max: int
) -> MergeQueueDecision:
    """Serial admission (§38.2 rule 2): features first, sweep last
    (ADR-U37 — sweep can never starve feature review), bounded by CI
    concurrency (F-16.1: the bound ships on by default)."""
    ordered = list(feature_prs) + list(sweep_prs)
    admit = ordered[:ci_concurrency_max]
    return MergeQueueDecision(
        admit=admit, deferred=ordered[ci_concurrency_max:],
        reason=f"serial queue, ci_concurrency_max={ci_concurrency_max}, "
               "sweep lowest priority")


class GepaBudget(BaseModel):
    targets: list[str] = Field(default_factory=list)  # which skills may evolve
    budget_rollouts_weekly: int = 0  # 0 = proposer disabled
    holdout_fixture_fraction: float = 0.2
    one_agent_per_cycle: bool = True


class GepaConfigError(RuntimeError):
    pass


def load_gepa_budget(mas_dir: str | pathlib.Path) -> GepaBudget:
    path = pathlib.Path(mas_dir) / GEPA_FILE
    if not path.exists():
        return GepaBudget()  # proposer off — the safe default
    raw = yaml.safe_load(path.read_text()) or {}
    budget = GepaBudget(**raw)
    if not 0 < budget.holdout_fixture_fraction < 1:
        raise GepaConfigError("holdout_fixture_fraction must be in (0,1) — an "
                              "optimizer scored on its own training fixtures "
                              "is overfitting with a budget")
    if budget.budget_rollouts_weekly and not budget.one_agent_per_cycle:
        raise GepaConfigError("one_agent_per_cycle is the floor: attributing a "
                              "regression requires changing one thing")
    return budget
