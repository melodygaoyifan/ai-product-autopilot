"""The upstream verdict vocabulary (doc 13) — typed, importable constants
so stages and routers speak one language instead of ad-hoc strings."""

from __future__ import annotations

APPROVALS = ("APPROVE_BRIEF", "APPROVE_PLAN", "APPROVE_SPEC")
BLOCKED = ("BLOCKED_MISSING_CONTEXT", "TASK_BLOCKED_MISSING_CONTEXT",
           "NEEDS_PROBE", "TASK_SCOPE_VIOLATION")
ESCALATIONS = (
    "ESCALATE_REQUIREMENT_CONFLICT",   # existed
    "ESCALATE_CONTRACT_BREAK",         # existed
    "ESCALATE_SCOPE_CREEP",
    "ESCALATE_ESTIMATE_BLOWN",
    "ESCALATE_DEPENDENCY_CYCLE",
    "ESCALATE_SPEC_GAP",               # the SCR trigger
    "ESCALATE_MIGRATION_DESTRUCTIVE",
    "ESCALATE_SECURITY_SURFACE",
    "ESCALATE_BUDGET_EXCEEDED",
    "ESCALATE_TOOL_FAILURE",
    "SPEC_DRIFT_UNDOCUMENTED",
)
ALL_VERDICTS = frozenset(APPROVALS + BLOCKED + ESCALATIONS)


def is_escalation(verdict: str) -> bool:
    return verdict in ESCALATIONS


def is_terminal(verdict: str) -> bool:
    """Approvals end a stage; escalations end it toward a human; BLOCKED
    verdicts end the attempt without pretending to a judgment."""
    return verdict in ALL_VERDICTS
