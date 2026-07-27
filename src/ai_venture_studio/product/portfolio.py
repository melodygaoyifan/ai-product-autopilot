"""P5 Portfolio Prioritization and the kill decision (§22.65).

The failure this stage exists against: a team runs an outer loop for a
year, every cycle concludes "we learned a lot, let's iterate," nothing is
ever killed, and the loop is revealed to have been a ratchet.

Kill criteria are authored at P2 — before anyone is attached — and
evaluated mechanically here; criteria authored after seeing the results
are rationalizations. Three structural rules, each closing an escape
hatch: a fired criterion mandates a recorded human decision (it cannot
lapse, be deferred, or be resolved by continuing to work — invariant
14.20); every PRD carries a loop budget whose exhaustion forces the same
review; kills are recorded, not deleted, so P0's Novelty voter surfaces
returning ideas with their history.

Gate PL5 routes to P0, P1, or P2 — NEVER directly into the inner loop. A
decision that jumped straight to coding would bypass the PRD, the
outcomes, and the kill criteria: the exact failure the outer loop exists
to prevent, arriving through its own back door.
"""

from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field, field_validator

from ai_venture_studio.product.claim_lint import ClaimIssue
from ai_venture_studio.product.kill_registry import (
    KILL_REGISTRY_FILE,
    KillRecord,
    load_kill_registry,
)

DEFAULT_MAX_LOOPS = 3

GATE_PL5_RUBRIC = (
    "Did any kill criterion fire, and what is the recorded decision?",
    "Which hypotheses are now falsified, and which claims does that invalidate?",
    "What did we spend, in attention and calendar, per unit of evidence gained?",
    "What is the single largest remaining unknown, and what is the cheapest "
    "test for it?",
    "Continue / pivot / kill / new opportunity — and what does the loser get?",
)


class KillCriterion(BaseModel):
    """A machine-evaluable kill criterion, e.g. 'O-1 misses 50% of target
    lift after 2 full P-loops'."""

    id: str
    text: str
    outcome_id: str
    min_target_lift_fraction: float  # fired when achieved/target lift < this
    after_loops: int


class OutcomeReadingSummary(BaseModel):
    outcome_id: str
    baseline: float
    target: float
    reading: float
    n: int


class KillEvaluation(BaseModel):
    fired: list[dict] = Field(default_factory=list)
    loop_budget_exhausted: bool
    requires_human_decision: bool
    legal_outcomes: list[str]


def evaluate_kill_criteria(
    criteria: list[KillCriterion],
    readings: dict[str, OutcomeReadingSummary],
    *,
    loops_elapsed: int,
    max_loops: int = DEFAULT_MAX_LOOPS,
) -> KillEvaluation:
    """Deterministic. Fires a MANDATORY human review; never decides. Note
    'continue unchanged' is absent from the legal outcomes once anything
    fires — that is the mechanism, not an oversight (§22.65.2)."""
    fired = []
    for criterion in criteria:
        if loops_elapsed < criterion.after_loops:
            continue
        reading = readings.get(criterion.outcome_id)
        if reading is None:
            continue  # Gate PL4 already demanded a reading-or-a-reason
        target_lift = reading.target - reading.baseline
        achieved_lift = reading.reading - reading.baseline
        fraction = achieved_lift / target_lift if target_lift else 0.0
        # Epsilon so exactly-at-threshold never fires on float representation
        # noise — a criterion that fires on 0.4999999999 "misses" is noise.
        if fraction < criterion.min_target_lift_fraction - 1e-9:
            fired.append(
                {
                    "criterion": criterion.text,
                    "reading": f"{criterion.outcome_id}: achieved "
                    f"{fraction:.0%} of target lift "
                    f"({reading.reading:g} vs target {reading.target:g}, "
                    f"baseline {reading.baseline:g}, n={reading.n})",
                }
            )
    exhausted = loops_elapsed >= max_loops
    return KillEvaluation(
        fired=fired,
        loop_budget_exhausted=exhausted,
        requires_human_decision=bool(fired) or exhausted,
        legal_outcomes=["kill", "pivot", "continue_with_revised_criteria"],
    )


class KillDecisionError(RuntimeError):
    """Invariant 14.20: a fired kill criterion cannot be closed without a
    recorded human decision — and 'continue unchanged' is not one."""


class GatePL5Decision(BaseModel):
    outcome: str  # kill | pivot | continue_with_revised_criteria | continue
    decider: str  # a named human, permanently (§22.65.1)
    reason: str
    route: str = ""  # p0 | p1 | p2 — never the inner loop
    revised_criteria: list[KillCriterion] = Field(default_factory=list)
    revision_evidence: str = ""  # required for continue_with_revised_criteria
    reusable_learning: str = ""
    revisit_if: str = ""

    @field_validator("decider")
    @classmethod
    def _named_human(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Gate PL5 is human, permanently (§22.65.1)")
        return value

    @field_validator("outcome")
    @classmethod
    def _legal(cls, value: str) -> str:
        legal = {"kill", "pivot", "continue_with_revised_criteria", "continue"}
        if value not in legal:
            raise ValueError(f"outcome must be one of {sorted(legal)}")
        return value

    @field_validator("route")
    @classmethod
    def _never_the_inner_loop(cls, value: str) -> str:
        if value and value not in {"p0", "p1", "p2"}:
            raise ValueError(
                "Gate PL5 routes to P0, P1, or P2 — never directly into the "
                "inner loop (§22.65.5); the back door is closed by the schema"
            )
        return value


def close_kill_evaluation(
    evaluation: KillEvaluation, decision: GatePL5Decision
) -> GatePL5Decision:
    """The only way past a fired criterion or an exhausted budget. Enforces
    invariant 14.20 and the revised-criteria honesty rule."""
    if evaluation.requires_human_decision:
        if decision.outcome == "continue":
            raise KillDecisionError(
                "'continue unchanged' is not a legal outcome once a criterion "
                "has fired or the loop budget is exhausted (§22.65.2)"
            )
        if decision.outcome == "continue_with_revised_criteria" and not (
            decision.revised_criteria and decision.revision_evidence.strip()
        ):
            raise KillDecisionError(
                "continue_with_revised_criteria requires new criteria AND new "
                "evidence justifying the revision — a real option honestly "
                "used, an obvious tell when abused"
            )
    if decision.outcome in {"kill", "pivot"} and not decision.reason.strip():
        raise KillDecisionError("a kill/pivot without a recorded reason is a "
                                "graveyard entry, not registry history")
    return decision


class KillRegistryWriteError(RuntimeError):
    """The registry is append-only. Rewriting history is not a merge
    conflict, it is the failure mode."""


def append_kill_record(
    mas_dir: str | pathlib.Path, record: KillRecord
) -> list[KillRecord]:
    """Append one record, preserving every existing entry byte-for-byte in
    meaning: the prior list is reloaded and must reappear unchanged."""
    existing = load_kill_registry(mas_dir)
    if any(r.id == record.id for r in existing):
        raise KillRegistryWriteError(
            f"registry already holds {record.id!r} — append-only means a new "
            "decision gets a new entry, not an edit"
        )
    updated = [*existing, record]
    path = pathlib.Path(mas_dir) / KILL_REGISTRY_FILE
    path.write_text(
        yaml.safe_dump([r.model_dump() for r in updated], sort_keys=False)
    )
    reloaded = load_kill_registry(mas_dir)
    if [r.model_dump() for r in reloaded[: len(existing)]] != [
        r.model_dump() for r in existing
    ]:
        raise KillRegistryWriteError("append mutated existing entries — aborting")
    return reloaded


# --- the loop-closing contract (§22.65.4) ------------------------------------


class CycleReport(BaseModel):
    """handoff/p4_to_p5.yaml — what P4 hands the portfolio stage."""

    prd_ref: str
    loop_index: int
    outcomes: list[dict] = Field(default_factory=list)
    hypothesis_verdicts: list[dict] = Field(default_factory=list)
    kill_evaluation: dict = Field(default_factory=dict)
    channel_health: dict = Field(default_factory=dict)
    attention_spent: dict[str, int] = Field(default_factory=dict)  # in approvals
    unknowns: list[str] = Field(default_factory=list)


class GatePL5Entry(BaseModel):
    passed: bool
    findings: list[str]


def gate_pl5_entry(
    report: CycleReport, backlog_lint: dict[str, list[ClaimIssue]]
) -> GatePL5Entry:
    """Entry: evidence bundle + kill evaluation + a REFRESHED backlog —
    stale claims are re-probed or downgraded before this gate, not during
    it (§22.65.5)."""
    findings = []
    if not report.kill_evaluation:
        findings.append("no kill evaluation in the cycle report")
    if not report.hypothesis_verdicts:
        findings.append("no hypothesis verdicts — the loop resolved nothing")
    if not report.attention_spent:
        findings.append("attention_spent missing — the budget cannot be tracked")
    for candidate, issues in sorted(backlog_lint.items()):
        stale = [i for i in issues if i.rule == "stale"]
        if stale:
            findings.append(
                f"backlog candidate {candidate!r} carries {len(stale)} stale "
                "claim(s) — re-probe or downgrade before the gate"
            )
    return GatePL5Entry(passed=not findings, findings=findings)
