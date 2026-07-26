"""The outer→inner handoff (§20.56.3) — p2_to_stage1.yaml.

The first of the two contracts between loops. Machine-checked at Stage 1
Discovery entry: a malformed handoff FAILS Discovery's DoR gate rather
than being interpreted. Discovery pins the exact PRD it read (prd_hash);
the hypothesis seed is class-mapped per §20.53.6 into the classes
Discovery's own Hypothesis model validates; regulatory constraints
inherited from Gate PL1 may not be weakened by Spec.
"""

from __future__ import annotations

import hashlib
import pathlib

import yaml
from pydantic import BaseModel, Field

from autoproduct.product.claims import ledger_class_for
from autoproduct.product.prd import PRD, SCOPE_TIERS
from autoproduct.upstream.discover import EVIDENCE_CLASSES


class HandoffError(RuntimeError):
    """A handoff that does not validate fails at the DoR gate — named
    errors, never interpretation."""


class SeedHypothesis(BaseModel):
    id: str
    statement: str
    class_: str = Field(alias="class")
    falsifier: str

    model_config = {"populate_by_name": True}


class Handoff(BaseModel):
    prd_ref: str
    prd_hash: str
    claim_ledger_ref: str
    hypothesis_seed: list[SeedHypothesis]
    scope_tier: str
    outcomes_ref: str
    constraints_inherited: list[dict] = Field(default_factory=list)


def _hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def emit_handoff(
    prd: PRD,
    prd_document_text: str,
    *,
    claim_ledger_ref: str,
    outcomes_ref: str,
    source_type_by_hypothesis: dict[str, str] | None = None,
    constraints_inherited: list[dict] | None = None,
) -> Handoff:
    """Build the contract from a linted PRD. Hypotheses map to Discovery's
    evidence classes via §20.53.6; unmapped hypotheses default to assumed —
    the honest class for a pre-launch demand hypothesis."""
    types = source_type_by_hypothesis or {}
    seed = [
        SeedHypothesis(
            id=h.id,
            statement=h.statement,
            **{"class": ledger_class_for(types[h.id]) if h.id in types else "assumed"},
            falsifier=h.falsifier,
        )
        for h in prd.demand_hypotheses
    ]
    return Handoff(
        prd_ref=prd.id,
        prd_hash=_hash_text(prd_document_text),
        claim_ledger_ref=claim_ledger_ref,
        hypothesis_seed=seed,
        scope_tier=prd.scope_tier,
        outcomes_ref=outcomes_ref,
        constraints_inherited=list(constraints_inherited or []),
    )


def write_handoff(handoff: Handoff, path: str | pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"handoff": handoff.model_dump(by_alias=True)}, sort_keys=False
        )
    )
    return path


def validate_handoff_at_dor(
    path: str | pathlib.Path, *, prd_document_text: str
) -> Handoff:
    """Discovery's DoR check (§20.56.3). Every failure is a named
    HandoffError — the gate never fills a gap with a guess."""
    try:
        raw = yaml.safe_load(pathlib.Path(path).read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise HandoffError(f"handoff unreadable: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("handoff"), dict):
        raise HandoffError("handoff file must contain a 'handoff' mapping")
    try:
        handoff = Handoff(**raw["handoff"])
    except ValueError as exc:
        raise HandoffError(f"malformed handoff: {exc}") from exc

    if handoff.scope_tier not in SCOPE_TIERS:
        raise HandoffError(
            f"scope_tier {handoff.scope_tier!r} not in {SCOPE_TIERS}"
        )
    actual = _hash_text(prd_document_text)
    if handoff.prd_hash != actual:
        raise HandoffError(
            f"prd_hash mismatch: handoff pins {handoff.prd_hash[:16]}…, the PRD "
            f"on disk hashes to {actual[:16]}… — Discovery reads exactly the PRD "
            "that passed Gate PL2, or nothing"
        )
    if not handoff.hypothesis_seed:
        raise HandoffError("handoff carries no hypothesis seed — the product "
                           "loop closes through these; an empty seed closes nothing")
    for hypothesis in handoff.hypothesis_seed:
        if hypothesis.class_ not in EVIDENCE_CLASSES:
            raise HandoffError(
                f"hypothesis {hypothesis.id}: class {hypothesis.class_!r} not in "
                f"Discovery's classes {sorted(EVIDENCE_CLASSES)}"
            )
        if not hypothesis.falsifier.strip():
            raise HandoffError(f"hypothesis {hypothesis.id} has no falsifier")
    for constraint in handoff.constraints_inherited:
        if not constraint.get("rule"):
            raise HandoffError(
                "inherited constraint lacks a rule — Spec cannot honor what "
                "Gate PL1 did not state"
            )
    return handoff
