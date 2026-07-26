"""Hypothesis reconciliation (§22.65.3) — how a bad P1 finding gets
corrected instead of persisting as institutional belief.

Every hypothesis — PRD demand hypotheses seeded through the handoff,
Discovery's own, market hypotheses from P1 — carries a falsifier and gets
a verdict at P4 against the PRE-STATED falsifier. Falsified hypotheses
invalidate the claims that depended on them, and the invalidation
propagates by claim ID into the backlog's evidence bundles. Claims declare
their dependencies via `hypothesis_refs`.
"""

from __future__ import annotations

from pydantic import BaseModel

VERDICTS = frozenset({"supported", "not_supported", "insufficient_evidence"})


class HypothesisVerdict(BaseModel):
    id: str
    verdict: str  # against the pre-stated falsifier, never a retrofit
    falsifier_met: bool = False
    evidence_ref: str = ""


class Invalidation(BaseModel):
    claim_id: str
    ledger: str
    hypothesis_id: str
    message: str


def falsified_ids(verdicts: list[HypothesisVerdict]) -> set[str]:
    return {
        v.id for v in verdicts if v.verdict == "not_supported" and v.falsifier_met
    }


def propagate_invalidations(
    verdicts: list[HypothesisVerdict], ledgers: dict[str, dict]
) -> list[Invalidation]:
    """Walk every ledger; any claim declaring a dependency on a falsified
    hypothesis is invalidated by ID — mechanically, not editorially."""
    falsified = falsified_ids(verdicts)
    invalidations = []
    for ledger_name, ledger in sorted(ledgers.items()):
        for claim in ledger.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            hit = falsified & set(claim.get("hypothesis_refs") or [])
            for hypothesis_id in sorted(hit):
                invalidations.append(
                    Invalidation(
                        claim_id=str(claim.get("id", "?")),
                        ledger=ledger_name,
                        hypothesis_id=hypothesis_id,
                        message=f"claim depends on falsified hypothesis "
                        f"{hypothesis_id} — downgrade or re-evidence before it "
                        "grounds anything again",
                    )
                )
    return invalidations
