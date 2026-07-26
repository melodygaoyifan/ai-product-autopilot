"""P2 Product Definition — the PRD schema, prd_lint, Gate PL2 (§20.56).

PRD ≠ spec, and the boundary is enforced: a PRD that contains EARS-shaped
sentences or names modules/interfaces is pre-empting Gate U2's scope lock,
and prd_lint fails it. Two fields carry unusual weight:
`instrumentation.exists: false` mechanically becomes a Planning task (the
structural answer to shipping a feature whose success metric was never
wired up), and `kill_criteria` is required at definition time, before
anyone is attached to the feature (§22.65.2 — criteria authored after the
results are rationalizations).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from autoproduct.evidence.metrics import MetricDefinition, metric_definition_check

SCOPE_TIERS = ("thin", "standard", "deep")

# EARS-shaped sentences belong to Stage 3 Spec, not the PRD.
_EARS_SHAPED = re.compile(
    r"^\s*(?:When|While|Where|If)\b.+?,\s*(?:then\s+)?the\s+.+?\s+shall\s+|"
    r"^\s*The\s+\S+\s+shall\s+",
    re.I | re.M,
)
# Module/interface naming: code identifiers, dotted module paths, endpoints.
_MODULE_SHAPED = re.compile(
    r"\b[a-z_][a-z0-9_]*\.py\b|"
    r"\b[a-z_][a-z0-9_]+(?:\.[a-z_][a-z0-9_]+){2,}\b|"
    r"\bclass\s+[A-Z][A-Za-z0-9]+\b|"
    r"(?:GET|POST|PUT|DELETE|PATCH)\s+/\S+|"
    r"`/api/\S+`"
)


class Instrumentation(BaseModel):
    event: str
    exists: bool


class OutcomeTarget(BaseModel):
    value: float
    by: str  # ISO date


class Outcome(BaseModel):
    id: str
    metric: str  # must be in the metric vocabulary (§22.62.3)
    definition_ref: str = ""
    baseline: dict = Field(default_factory=dict)
    target: OutcomeTarget
    instrumentation: Instrumentation


class PRDDemandHypothesis(BaseModel):
    id: str
    statement: str
    falsifier: str
    check: dict = Field(default_factory=dict)  # {stage, method, window_days}


class PRD(BaseModel):
    id: str
    problem_statement: str
    evidence_refs: list[str]  # must resolve into the claim ledger
    affected_segment: dict = Field(default_factory=dict)
    non_goals: list[str] = Field(default_factory=list)
    outcomes: list[Outcome] = Field(default_factory=list)
    demand_hypotheses: list[PRDDemandHypothesis] = Field(default_factory=list)
    scope_tier: str
    kill_criteria: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    @field_validator("scope_tier")
    @classmethod
    def _tier(cls, value: str) -> str:
        if value not in SCOPE_TIERS:
            raise ValueError(f"scope_tier must be one of {SCOPE_TIERS}")
        return value


class PrdIssue(BaseModel):
    rule: str
    message: str


class PlanningTask(BaseModel):
    outcome_id: str
    event: str
    title: str


def prd_lint(
    prd: PRD,
    prd_prose: str,
    *,
    vocabulary: dict[str, MetricDefinition],
    ledger_claim_ids: set[str],
) -> tuple[list[PrdIssue], list[PlanningTask]]:
    """Returns (issues, generated planning tasks). Issues block Gate PL2;
    an uninstrumented outcome is not an issue — it is a task."""
    issues: list[PrdIssue] = []
    tasks: list[PlanningTask] = []

    match = _EARS_SHAPED.search(prd_prose)
    if match:
        issues.append(
            PrdIssue(
                rule="ears_leakage",
                message=f"EARS-shaped sentence in the PRD ({match.group(0).strip()[:60]!r}) "
                "— acceptance criteria belong to Stage 3 Spec",
            )
        )
    match = _MODULE_SHAPED.search(prd_prose)
    if match:
        issues.append(
            PrdIssue(
                rule="module_leakage",
                message=f"PRD names modules/interfaces ({match.group(0)!r}) — "
                "implementation pre-empts scope lock (§20.56.1)",
            )
        )
    if len(prd.non_goals) < 2:
        issues.append(
            PrdIssue(
                rule="missing_non_goals",
                message="a PRD with fewer than 2 non-goals is a wish (§20.56.2)",
            )
        )
    if not prd.kill_criteria:
        issues.append(
            PrdIssue(
                rule="missing_kill_criteria",
                message="kill criteria are required at definition time, before "
                "anyone is attached (§22.65.2)",
            )
        )
    if not prd.outcomes:
        issues.append(
            PrdIssue(rule="no_outcomes", message="a PRD needs >=1 measurable outcome")
        )
    for issue in metric_definition_check(
        [o.metric for o in prd.outcomes], vocabulary
    ):
        issues.append(PrdIssue(rule="undefined_metric", message=issue.message))
    for outcome in prd.outcomes:
        if not outcome.instrumentation.exists:
            tasks.append(
                PlanningTask(
                    outcome_id=outcome.id,
                    event=outcome.instrumentation.event,
                    title=f"Instrument {outcome.instrumentation.event!r} so outcome "
                    f"{outcome.id} is measurable before launch",
                )
            )
    unresolved = [r for r in prd.evidence_refs if r not in ledger_claim_ids]
    if unresolved:
        issues.append(
            PrdIssue(
                rule="unresolved_evidence_refs",
                message=f"evidence_refs {unresolved} do not resolve into the claim ledger",
            )
        )
    for hypothesis in prd.demand_hypotheses:
        if not hypothesis.falsifier.strip():
            issues.append(
                PrdIssue(
                    rule="unfalsifiable_hypothesis",
                    message=f"hypothesis {hypothesis.id} states no falsifier",
                )
            )
    return issues, tasks


GATE_PL2_RUBRIC = (
    "Do the kill criteria bite — would this feature actually be killed if they fired?",
    "Is every outcome measurable, with instrumentation that exists or is now a task?",
    "Is the scope tier honest given the size range?",
)


class GatePL2Decision(BaseModel):
    acknowledged_kill_criteria: bool
    scope_tier: str
    decider: str

    @field_validator("decider")
    @classmethod
    def _named_human(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Gate PL2 is human — brief, but human (§20.56.4)")
        return value
