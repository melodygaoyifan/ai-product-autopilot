"""Gate PL4 (§22.62.2) — deterministic: every PRD outcome has a
reading-or-a-reason, and the evidence ledger is clean.

"Reason" is a first-class outcome, not an excuse slot: insufficient_evidence
with a stated required n, or window_incomplete with the date the window
closes. What cannot pass is silence — an outcome nobody read and nobody
explained is how a product loop stops being a loop.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from ai_venture_studio.evidence.cohort import CohortReading

LEGAL_REASONS = frozenset(
    {"insufficient_evidence", "window_incomplete", "instrumentation_pending"}
)


class OutcomeReason(BaseModel):
    outcome_id: str
    reason: str
    detail: str  # required: what it would take to know, or when the window closes

    @field_validator("reason")
    @classmethod
    def _legal(cls, value: str) -> str:
        if value not in LEGAL_REASONS:
            raise ValueError(f"reason must be one of {sorted(LEGAL_REASONS)}")
        return value

    @field_validator("detail")
    @classmethod
    def _substantive(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a reason without detail is silence with paperwork")
        return value


class GatePL4Result(BaseModel):
    passed: bool
    missing_outcomes: list[str] = Field(default_factory=list)
    ledger_issues: int = 0
    detail: str = ""


def gate_pl4(
    prd_outcome_ids: list[str],
    readings: dict[str, CohortReading],
    reasons: list[OutcomeReason],
    ledger_issue_count: int,
) -> GatePL4Result:
    reasoned = {r.outcome_id for r in reasons}
    missing = [
        oid for oid in prd_outcome_ids if oid not in readings and oid not in reasoned
    ]
    passed = not missing and ledger_issue_count == 0
    return GatePL4Result(
        passed=passed,
        missing_outcomes=missing,
        ledger_issues=ledger_issue_count,
        detail=(
            "every PRD outcome has a reading-or-a-reason; ledger clean"
            if passed
            else f"missing outcomes: {missing}; ledger issues: {ledger_issue_count}"
        ),
    )
