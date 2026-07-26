"""P0 Opportunity Sensing — clustering and Gate PL0 (§20.54).

Does: cluster real signals from declared-standing sources into candidate
opportunities and check the candidate set is well-formed. Does not: decide
what to build, or synthesize demand no signal shows. There is deliberately
no Desirability judgment at P0 — desirability is a market question and
belongs to P1 with its own evidence discipline.

Clustering is deterministic near-dup FIRST (ADR-U05 ordering); an
embedding pass may refine clusters later but never replaces this layer.
Gate PL0 passing means "a ranked candidate set exists and is well-formed,"
not "these are good ideas."
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from autoproduct.product.claim_lint import lint_ledger
from autoproduct.product.claims import ProductPolicy
from autoproduct.product.kill_registry import KillMatch, KillRecord, match_killed
from autoproduct.textsim import similarity

CLUSTER_THRESHOLD = 0.35  # signals are short free text; tuned like kill-match


class RawSignal(BaseModel):
    id: str
    source_id: str  # must exist in .mas/signal-sources.yaml (standing rule)
    text: str
    locator: str = ""


class SignalCluster(BaseModel):
    signal_ids: list[str]
    representative: str  # the longest member — never a synthesized summary


class DemandHypothesis(BaseModel):
    statement: str
    falsifier: str


class OpportunityCandidate(BaseModel):
    id: str
    statement: str
    demand_hypothesis: DemandHypothesis
    cheapest_test: str  # named, concrete (landing page, concierge run, probe)
    claim_ledger: dict = Field(default_factory=dict)
    signal_refs: list[str] = Field(default_factory=list)
    killed_matches: list[KillMatch] = Field(default_factory=list)


class GatePL0Finding(BaseModel):
    candidate_id: str = ""
    rule: str
    message: str


class GatePL0Result(BaseModel):
    passed: bool
    findings: list[GatePL0Finding]
    ranked_candidate_ids: list[str]


def cluster_signals(
    signals: list[RawSignal], *, threshold: float = CLUSTER_THRESHOLD
) -> list[SignalCluster]:
    """Greedy deterministic near-dup clustering: a signal joins the first
    cluster whose representative it resembles, else starts its own."""
    clusters: list[list[RawSignal]] = []
    for signal in signals:
        for members in clusters:
            anchor = max(members, key=lambda s: len(s.text))
            if similarity(signal.text, anchor.text, k=3) >= threshold:
                members.append(signal)
                break
        else:
            clusters.append([signal])
    return [
        SignalCluster(
            signal_ids=[s.id for s in members],
            representative=max(members, key=lambda s: len(s.text)).text,
        )
        for members in clusters
    ]


def gate_pl0(
    candidates: list[OpportunityCandidate],
    kill_registry: list[KillRecord],
    *,
    today: dt.date | None = None,
    policy: ProductPolicy | None = None,
    min_candidates: int = 3,
) -> GatePL0Result:
    """Deterministic, no human (§20.54.4). BLOCKED rather than passed when
    the set is thin — an empty ranked set is not a ranked set."""
    findings: list[GatePL0Finding] = []
    if len(candidates) < min_candidates:
        findings.append(
            GatePL0Finding(
                rule="insufficient_candidates",
                message=f"{len(candidates)} candidate(s) < {min_candidates} — BLOCKED",
            )
        )

    for candidate in candidates:
        issues = lint_ledger(
            candidate.claim_ledger, "opportunity", today=today, policy=policy
        )
        for issue in issues:
            findings.append(
                GatePL0Finding(
                    candidate_id=candidate.id,
                    rule=f"claim_lint:{issue.rule}",
                    message=issue.message,
                )
            )
        claims = candidate.claim_ledger.get("claims") or []
        if not any(
            isinstance(c, dict) and c.get("source_type") != "model_inference"
            for c in claims
        ):
            findings.append(
                GatePL0Finding(
                    candidate_id=candidate.id,
                    rule="no_grounding_signal",
                    message="every candidate needs >=1 non-model_inference claim — "
                    "an opportunity no signal shows is synthesized demand",
                )
            )
        if not candidate.demand_hypothesis.falsifier.strip():
            findings.append(
                GatePL0Finding(
                    candidate_id=candidate.id,
                    rule="unfalsifiable_hypothesis",
                    message="demand hypothesis states no disconfirming observation",
                )
            )
        if not candidate.cheapest_test.strip():
            findings.append(
                GatePL0Finding(
                    candidate_id=candidate.id,
                    rule="no_cheapest_test",
                    message="no named cheapest test — 'build it' is not a test",
                )
            )
        # Kill-registry check is surfacing, not blocking: history informs
        # the human at PL1, it does not veto at PL0.
        candidate.killed_matches = match_killed(candidate.statement, kill_registry)

    return GatePL0Result(
        passed=not findings,
        findings=findings,
        ranked_candidate_ids=[c.id for c in candidates],
    )
