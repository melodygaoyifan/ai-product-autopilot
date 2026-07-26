"""The five outer-loop metrics (§22.66.4) — mirroring the five upstream
and five downstream.

The last one is deliberately aimed at this framework itself: a design that
adds six stages to a system should say how it would know it made things
worse. If attention cost per resolved hypothesis does not improve over
quarters, the product loop is not paying for itself and should be
simplified or dropped.
"""

from __future__ import annotations

from pydantic import BaseModel

from autoproduct.product.kill_registry import KillRecord
from autoproduct.product.reconcile import HypothesisVerdict

_STRONG_TYPES = frozenset({"primary_measured", "primary_cited"})


class LoopMetrics(BaseModel):
    evidence_quality_ratio: dict[str, float]  # by stage; watch the trend
    hypothesis_resolution_rate: float
    decision_latency_days: dict[str, float]  # per gate
    kill_rate: float | None  # None until anything was decided at PL5
    attention_cost_per_resolved_hypothesis: float | None


def evidence_quality_ratio(ledgers_by_stage: dict[str, dict]) -> dict[str, float]:
    """Share of claims that are primary_measured or primary_cited, by
    stage — the outer loop's analogue of test coverage."""
    ratios = {}
    for stage, ledger in sorted(ledgers_by_stage.items()):
        claims = [c for c in ledger.get("claims") or [] if isinstance(c, dict)]
        if not claims:
            ratios[stage] = 0.0
            continue
        strong = sum(1 for c in claims if c.get("source_type") in _STRONG_TYPES)
        ratios[stage] = strong / len(claims)
    return ratios


def hypothesis_resolution_rate(verdicts: list[HypothesisVerdict]) -> float:
    """Falsified-or-confirmed ÷ total open, per loop. A loop that resolves
    nothing is a ratchet."""
    if not verdicts:
        return 0.0
    resolved = sum(1 for v in verdicts if v.verdict in ("supported", "not_supported"))
    return resolved / len(verdicts)


def decision_latency_days(
    gate_entries: dict[str, str], gate_decisions: dict[str, str]
) -> dict[str, float]:
    """Gate entry → recorded decision, in days (ISO timestamps in, so the
    caller supplies time — nothing here reads a clock). The first thing to
    degrade under attention starvation."""
    import datetime as dt

    latencies = {}
    for gate, entered in sorted(gate_entries.items()):
        decided = gate_decisions.get(gate)
        if decided is None:
            continue
        delta = dt.datetime.fromisoformat(decided) - dt.datetime.fromisoformat(entered)
        latencies[gate] = round(delta.total_seconds() / 86400, 3)
    return latencies


def kill_rate(registry: list[KillRecord], decided_at_pl5: int) -> float | None:
    """Killed-or-pivoted ÷ decided at Gate PL5. There is no correct target
    — a stated rate near zero over many loops is itself the finding."""
    if decided_at_pl5 <= 0:
        return None
    stopped = sum(1 for r in registry if r.outcome in ("kill", "pivot"))
    return stopped / decided_at_pl5


def attention_cost_per_resolved_hypothesis(
    attention_spent: dict[str, int], verdicts: list[HypothesisVerdict]
) -> float | None:
    """Human approvals ÷ hypotheses resolved — the number by which the
    whole product loop is falsifiable."""
    resolved = sum(1 for v in verdicts if v.verdict in ("supported", "not_supported"))
    if resolved == 0:
        return None
    return sum(attention_spent.values()) / resolved


def loop_metrics(
    *,
    ledgers_by_stage: dict[str, dict],
    verdicts: list[HypothesisVerdict],
    gate_entries: dict[str, str],
    gate_decisions: dict[str, str],
    registry: list[KillRecord],
    decided_at_pl5: int,
    attention_spent: dict[str, int],
) -> LoopMetrics:
    return LoopMetrics(
        evidence_quality_ratio=evidence_quality_ratio(ledgers_by_stage),
        hypothesis_resolution_rate=hypothesis_resolution_rate(verdicts),
        decision_latency_days=decision_latency_days(gate_entries, gate_decisions),
        kill_rate=kill_rate(registry, decided_at_pl5),
        attention_cost_per_resolved_hypothesis=attention_cost_per_resolved_hypothesis(
            attention_spent, verdicts
        ),
    )
