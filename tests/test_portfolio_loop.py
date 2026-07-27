"""P5 kill machinery, reconciliation, loop metrics — and the v3.0.0 gate:
one full loop with a recorded kill decision that demonstrably could not be
closed without one, its learning surfacing in the next P0 pass, and the
attention-cost baseline computed.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from ai_venture_studio.evidence import AnalyticsStore, cohort_calc
from ai_venture_studio.evidence.metrics import MetricDefinition
from ai_venture_studio.product import (
    CycleReport,
    DemandHypothesis,
    GatePL5Decision,
    HypothesisVerdict,
    KillCriterion,
    KillDecisionError,
    KillRegistryWriteError,
    KillRecord,
    OpportunityCandidate,
    OutcomeReadingSummary,
    append_kill_record,
    close_kill_evaluation,
    evaluate_kill_criteria,
    gate_pl0,
    gate_pl5_entry,
    lint_ledger,
    load_kill_registry,
    loop_metrics,
    propagate_invalidations,
)

PORTFOLIO = Path(__file__).parent / "fixtures" / "portfolio"
TODAY = dt.date(2026, 7, 26)


def _fixtures():
    return yaml.safe_load((PORTFOLIO / "kill_criteria.yaml").read_text())["fixtures"]


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda f: f["label"])
def test_kill_criteria_fixture(fixture):
    inp = fixture["input"]
    evaluation = evaluate_kill_criteria(
        [KillCriterion(**c) for c in inp["criteria"]],
        {k: OutcomeReadingSummary(**v) for k, v in inp["readings"].items()},
        loops_elapsed=inp["loops_elapsed"],
    )
    expect = fixture["expect"]
    assert len(evaluation.fired) == expect["fired"]
    assert evaluation.requires_human_decision is expect["requires_human"]
    assert evaluation.loop_budget_exhausted is expect["budget_exhausted"]
    assert "continue" not in evaluation.legal_outcomes  # never, once evaluated


def test_kill_fixture_gate_is_the_standing_eight():
    assert len(_fixtures()) == 8


# --- invariant 14.20: a fired criterion cannot be closed silently ---------------


def _fired_evaluation():
    return evaluate_kill_criteria(
        [KillCriterion(id="K-1", text="O-1 misses 50% after 2 loops",
                       outcome_id="O-1", min_target_lift_fraction=0.5, after_loops=2)],
        {"O-1": OutcomeReadingSummary(
            outcome_id="O-1", baseline=0.11, target=0.18, reading=0.128, n=1840)},
        loops_elapsed=2,
    )


def test_a_fired_criterion_demands_a_real_decision():
    evaluation = _fired_evaluation()
    with pytest.raises(KillDecisionError, match="not a legal outcome"):
        close_kill_evaluation(
            evaluation,
            GatePL5Decision(outcome="continue", decider="melody", reason="momentum"),
        )
    with pytest.raises(KillDecisionError, match="new criteria AND new evidence"):
        close_kill_evaluation(
            evaluation,
            GatePL5Decision(
                outcome="continue_with_revised_criteria", decider="melody",
                reason="the segment shifted",
            ),
        )
    with pytest.raises(KillDecisionError, match="reason"):
        close_kill_evaluation(
            evaluation, GatePL5Decision(outcome="kill", decider="melody", reason=" ")
        )
    with pytest.raises(ValueError, match="human"):
        GatePL5Decision(outcome="kill", decider="", reason="x")
    closed = close_kill_evaluation(
        evaluation,
        GatePL5Decision(
            outcome="kill", decider="melody",
            reason="activation lift 26% of target across 2 loops; no cohort showed it",
        ),
    )
    assert closed.outcome == "kill"


def test_gate_pl5_never_routes_into_the_inner_loop():
    with pytest.raises(ValueError, match="never directly into the inner loop"):
        GatePL5Decision(outcome="pivot", decider="melody", reason="r", route="stage4")
    GatePL5Decision(outcome="pivot", decider="melody", reason="r", route="p1")


# --- the append-only registry writer ----------------------------------------------


def _record(rid: str) -> KillRecord:
    return KillRecord(
        id=rid, decided_at="2026-07-26", outcome="kill",
        reason="activation lift 26% of target across 2 loops",
        statement="one-click bulk export onboarding for recruiting ops",
        reusable_learning="export-first onboarding does not motivate this segment",
        revisit_if="we acquire a segment with existing structured data",
    )


def test_registry_writer_appends_and_never_edits(tmp_path):
    first = append_kill_record(tmp_path, _record("PRD-2026-009"))
    assert [r.id for r in first] == ["PRD-2026-009"]
    second = append_kill_record(tmp_path, _record("PRD-2026-014"))
    assert [r.id for r in second] == ["PRD-2026-009", "PRD-2026-014"]
    assert second[0].reusable_learning  # history intact, byte-for-meaning
    with pytest.raises(KillRegistryWriteError, match="append-only"):
        append_kill_record(tmp_path, _record("PRD-2026-009"))


# --- reconciliation (§22.65.3) ------------------------------------------------------


def test_falsified_hypotheses_invalidate_dependent_claims_by_id():
    verdicts = [
        HypothesisVerdict(id="H-1", verdict="not_supported", falsifier_met=True),
        HypothesisVerdict(id="H-2", verdict="insufficient_evidence"),
    ]
    ledgers = {
        "market": {"claims": [
            {"id": "C-7", "hypothesis_refs": ["H-1"]},
            {"id": "C-8", "hypothesis_refs": ["H-2"]},
        ]},
        "opportunity": {"claims": [{"id": "C-2", "hypothesis_refs": ["H-1", "H-9"]}]},
    }
    invalidations = propagate_invalidations(verdicts, ledgers)
    assert [(i.ledger, i.claim_id) for i in invalidations] == [
        ("market", "C-7"), ("opportunity", "C-2"),
    ]  # H-2 is unresolved, not falsified — its claims stand


# --- Gate PL5 entry -------------------------------------------------------------------


def test_gate_pl5_entry_demands_a_refreshed_backlog():
    report = CycleReport(
        prd_ref="PRD-2026-014", loop_index=2,
        hypothesis_verdicts=[{"id": "H-1", "verdict": "not_supported"}],
        kill_evaluation={"fired": []},
        attention_spent={"gate_pl3": 11},
    )
    stale_ledger = {"claims": [{
        "id": "C-9", "text": "Vendor C add-on at $199", "source_type": "primary_cited",
        "evidence": [{"method": "probe", "locator": "https://vendor-c.example/p",
                      "retrieved_at": "2026-02-01T10:00:00Z",
                      "artifact_hash": "sha256:" + "1" * 64}],
        "falsifier": "re-probe differs", "expires": "2026-05-01",
    }]}
    entry = gate_pl5_entry(
        report, {"cand-a": lint_ledger(stale_ledger, "market", today=TODAY)}
    )
    assert not entry.passed and any("stale" in f for f in entry.findings)
    clean = gate_pl5_entry(report, {"cand-a": []})
    assert clean.passed


# --- the v3.0.0 gate: one full loop, closed with a recorded kill ---------------------


def test_the_loop_closes_with_a_recorded_kill_and_the_learning_survives(tmp_path):
    # P4 — the real reading, through the boundary: 32 of 250 activated (12.8%).
    events = []
    for i in range(250):
        events.append({"unit": f"u{i}", "signup_week": "w1", "event": "workspace.created"})
        if i < 32:
            events.append({"unit": f"u{i}", "signup_week": "w1",
                           "event": "workspace.first_export"})
    (reading,) = cohort_calc(
        AnalyticsStore(events),
        MetricDefinition(id="activation_rate", definition="…",
                         numerator_event="workspace.first_export", window_days=7),
        cohort_field="signup_week", cohort_start=dt.date(2026, 7, 1), today=TODAY,
    )
    assert reading.value == pytest.approx(0.128)

    # The criterion authored at P2 fires on it after two loops.
    evaluation = evaluate_kill_criteria(
        [KillCriterion(id="K-1", text="O-1 misses 50% of target lift after 2 loops",
                       outcome_id="O-1", min_target_lift_fraction=0.5, after_loops=2)],
        {"O-1": OutcomeReadingSummary(outcome_id="O-1", baseline=0.11, target=0.18,
                                      reading=reading.value, n=reading.n)},
        loops_elapsed=2,
    )
    assert evaluation.requires_human_decision

    # P4→P5 contract; entry passes on a refreshed backlog.
    report = CycleReport(
        prd_ref="PRD-2026-014", loop_index=2,
        outcomes=[{"id": "O-1", "target": 0.18, "reading": reading.value,
                   "n": reading.n, "method": "cohort",
                   "source_type": "primary_measured"}],
        hypothesis_verdicts=[{"id": "H-1", "verdict": "not_supported",
                              "falsifier_met": True}],
        kill_evaluation=evaluation.model_dump(),
        attention_spent={"gate_pl1": 1, "gate_pl2": 1, "gate_pl3": 11, "gate_pl5": 1},
    )
    assert gate_pl5_entry(report, {"cand-b": []}).passed

    # Gate PL5 — the human records the kill; the registry takes the history.
    decision = close_kill_evaluation(
        evaluation,
        GatePL5Decision(
            outcome="kill", decider="melody",
            reason="activation lift 26% of target across 2 loops; no cohort showed it",
            reusable_learning="export-first onboarding does not motivate this segment",
            revisit_if="we acquire a segment with existing structured data",
        ),
    )
    append_kill_record(tmp_path, KillRecord(
        id="PRD-2026-014", decided_at="2026-07-26", outcome=decision.outcome,
        reason=decision.reason,
        statement="one-click bulk export onboarding for recruiting ops",
        hypotheses_falsified=["H-1"],
        reusable_learning=decision.reusable_learning,
        revisit_if=decision.revisit_if,
    ))

    # Falsified H-1 invalidates the market claim that leaned on it.
    invalidations = propagate_invalidations(
        [HypothesisVerdict(id="H-1", verdict="not_supported", falsifier_met=True)],
        {"market": {"claims": [{"id": "C-14", "hypothesis_refs": ["H-1"]}]}},
    )
    assert [i.claim_id for i in invalidations] == ["C-14"]

    # The loop actually closes: the next P0 pass surfaces the kill, with
    # its revisit condition, on a returning near-identical candidate.
    registry = load_kill_registry(tmp_path)
    returning = OpportunityCandidate(
        id="cand-return",
        statement="one-click bulk export onboarding for recruiting ops teams",
        demand_hypothesis=DemandHypothesis(statement="s", falsifier="f"),
        cheapest_test="stub",
        claim_ledger={"claims": [{"id": "C-1", "text": "tickets cluster on export pain",
                                  "source_type": "user_reported", "n": 12,
                                  "evidence": [{"method": "ticket_cluster",
                                                "locator": "evidence://t",
                                                "retrieved_at": "2026-07-23T16:20:00Z"}],
                                  "falsifier": "fewer than 5 reporters"}]},
    )
    gate_pl0([returning] * 3, registry, today=TODAY)
    assert returning.killed_matches
    assert "structured data" in returning.killed_matches[0].record.revisit_if

    # And the attention-cost baseline is published with the cycle.
    metrics = loop_metrics(
        ledgers_by_stage={"market": {"claims": [
            {"id": "C-2", "source_type": "primary_cited"},
            {"id": "C-3", "source_type": "model_inference"},
        ]}},
        verdicts=[HypothesisVerdict(id="H-1", verdict="not_supported",
                                    falsifier_met=True)],
        gate_entries={"gate_pl5": "2026-07-25T09:00:00"},
        gate_decisions={"gate_pl5": "2026-07-26T09:00:00"},
        registry=registry,
        decided_at_pl5=1,
        attention_spent=report.attention_spent,
    )
    assert metrics.evidence_quality_ratio["market"] == 0.5
    assert metrics.hypothesis_resolution_rate == 1.0
    assert metrics.decision_latency_days["gate_pl5"] == 1.0
    assert metrics.kill_rate == 1.0
    assert metrics.attention_cost_per_resolved_hypothesis == 14.0
