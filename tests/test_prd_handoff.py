"""P2 PRD stage + the outer→inner handoff (doc 20 §56, week P13) — and the
v2.4.0 release gate: one opportunity travels P0→P1→P2→Stage 1 with the
handoff machine-checked at Discovery's DoR gate.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from ai_venture_studio.evidence import load_metric_vocabulary
from ai_venture_studio.product import (
    PRD,
    DemandHypothesis,
    GatePL1Decision,
    GatePL2Decision,
    HandoffError,
    OpportunityCandidate,
    RawSignal,
    cluster_signals,
    emit_handoff,
    gate_pl0,
    gate_pl1_entry,
    prd_lint,
    record_probe,
    sizing_calc,
    validate_handoff_at_dor,
    write_handoff,
)
from ai_venture_studio.product.sizing import SizingFactor
from ai_venture_studio.product.sources import SignalSourceError, load_signal_sources
from ai_venture_studio.upstream.discover import Hypothesis

UPSTREAM = Path(__file__).parent / "fixtures" / "upstream"
REPO_METRICS = Path(__file__).parent.parent / "metrics"
TODAY = dt.date(2026, 7, 26)
VOCABULARY = load_metric_vocabulary(REPO_METRICS)


# --- prd_lint fixture gate ----------------------------------------------------


def _prd_fixtures():
    return yaml.safe_load((UPSTREAM / "prd_lint.yaml").read_text())["fixtures"]


@pytest.mark.parametrize("fixture", _prd_fixtures(), ids=lambda f: f["label"])
def test_prd_lint_fixture(fixture):
    prd = PRD(**fixture["input"]["prd"])
    issues, tasks = prd_lint(
        prd,
        fixture["input"]["prose"],
        vocabulary=VOCABULARY,
        ledger_claim_ids={"C-1"},
    )
    assert {i.rule for i in issues} == set(fixture["expect"]["rules"])
    assert len(tasks) == fixture["expect"]["tasks"]
    for task in tasks:  # the uninstrumented outcome became a Planning task
        assert task.event and task.outcome_id


def test_prd_fixture_gate_is_the_standing_eight():
    assert len(_prd_fixtures()) == 8


def test_instrumentation_event_must_match_the_metric_numerator():
    # Found by the first real-provider smoke: the PRD instrumented
    # 'build_progress_panel_opened' while the definition counts
    # 'build.progress_panel_viewed' — P4 would have read zero.
    fixture = yaml.safe_load((UPSTREAM / "prd_lint.yaml").read_text())
    prd_dict = dict(fixture["fixtures"][6]["input"]["prd"])  # the clean PRD
    prd_dict["outcomes"] = [dict(prd_dict["outcomes"][0],
                                 instrumentation={"event": "workspace.exported",
                                                  "exists": True})]
    issues, _ = prd_lint(
        PRD(**prd_dict), fixture["fixtures"][6]["input"]["prose"],
        vocabulary=VOCABULARY, ledger_claim_ids={"C-1"},
    )
    assert [i.rule for i in issues] == ["instrumentation_event_mismatch"]
    assert "workspace.first_export" in issues[0].message  # names the fix


def test_gate_decisions_require_named_humans_and_complete_outcomes():
    with pytest.raises(ValueError, match="human"):
        GatePL1Decision(outcome="pursue", decider=" ", scope_tier="standard")
    decision = GatePL1Decision(outcome="test_first", decider="melody", named_test="")
    with pytest.raises(ValueError, match="named cheapest test"):
        decision.validate_completeness()
    GatePL1Decision(
        outcome="pursue", decider="melody", scope_tier="standard"
    ).validate_completeness()
    with pytest.raises(ValueError, match="human"):
        GatePL2Decision(acknowledged_kill_criteria=True, scope_tier="standard", decider="")


# --- the v2.4.0 gate: one opportunity, P0 → P1 → P2 → Stage 1 -------------------


def test_one_opportunity_travels_the_whole_upstream_path(tmp_path):
    mas = tmp_path
    (mas / "signal-sources.yaml").write_text(
        "- id: support-tickets\n  standing: first-party, ours\n"
        "  match: ['evidence://']\n"
        "- id: vendor-pages\n  standing: public + official pages\n"
        "  match: ['https://vendor-a.example/', 'https://vendor-b.example/']\n"
    )
    sources = load_signal_sources(mas)

    # P0 — signals cluster into a grounded, falsifiable candidate set.
    signals = [
        RawSignal(id=f"s{i}", source_id="support-tickets",
                  text="Bulk export to CSV takes forever from the reports page")
        for i in range(3)
    ]
    assert len(cluster_signals(signals)) == 1
    ledger = {
        "claims": [
            {
                "id": "C-1",
                "text": "Support tickets cluster on manual CSV export pain",
                "kind": "user_need",
                "source_type": "user_reported",
                "n": 12,
                "evidence": [{"method": "ticket_cluster",
                              "locator": "evidence://tickets/export-pain",
                              "retrieved_at": "2026-07-23T16:20:00Z"}],
                "falsifier": "cluster resolves to fewer than 5 distinct reporters",
            }
        ]
    }
    candidates = [
        OpportunityCandidate(
            id=f"cand-{letter}",
            statement=f"Reduce manual export pain, framing {letter}",
            demand_hypothesis=DemandHypothesis(
                statement="admins will adopt one-click bulk export",
                falsifier="under 5% of active workspaces click the stub in 2 weeks",
            ),
            cheapest_test="bulk-export stub behind a click counter",
            claim_ledger=ledger,
        )
        for letter in "abc"
    ]
    assert gate_pl0(candidates, [], today=TODAY).passed

    # P1 — probes are snapshotted with standing; sizing is a range; the
    # market ledger passes the deterministic Gate PL1 entry.
    probe = record_probe(
        b"<html>Vendor A: $49/seat, bulk export in beta</html>",
        locator="https://vendor-a.example/pricing",
        retrieved_at="2026-07-20T09:00:00Z",
        sources=sources,
        mas_dir=mas,
    )
    with pytest.raises(SignalSourceError, match="no standing"):
        record_probe(b"x", locator="https://scraped.example/x",
                     retrieved_at="2026-07-20T09:00:00Z", sources=sources, mas_dir=mas)

    sizing = sizing_calc(
        [
            SizingFactor(name="addressable_orgs", value=4200,
                         source_type="primary_cited", sensitivity=(3000, 5000)),
            SizingFactor(name="annual_contract_value", value=3600,
                         source_type="primary_measured", n=27),
        ]
    )
    assert sizing.status == "ok"

    market_ledger = {
        "claims": [
            {
                "id": "C-2",
                "text": "Vendor A lists bulk export as beta at $49 per seat",
                "kind": "competitor_fact",
                "source_type": "primary_cited",
                "evidence": [probe],
                "falsifier": "the snapshotted pricing page shows no bulk-export beta",
            },
            *ledger["claims"],
        ]
    }
    entry = gate_pl1_entry(
        market_ledger, sizing, mas_dir=mas,
        disconfirmation_answered=True, regulatory_triaged=True, today=TODAY,
    )
    assert entry.passed, entry.findings
    GatePL1Decision(
        outcome="pursue", decider="melody", scope_tier="standard"
    ).validate_completeness()

    # P2 — the PRD lints clean and the uninstrumented outcome becomes a task.
    prd = PRD(
        id="PRD-2026-014",
        problem_statement="Recruiting ops teams lose hours weekly to manual exports.",
        evidence_refs=["C-1", "C-2"],
        affected_segment={"name": "mid-market recruiting ops", "size_claim": "C-1"},
        non_goals=["No custom report builder this cycle.",
                   "No new segment beyond workspace admins."],
        outcomes=[{
            "id": "O-1",
            "metric": "activation_rate",
            "definition_ref": "metrics/activation_rate.md",
            "baseline": {"value": 0.11, "source_type": "primary_measured", "n": 1840},
            "target": {"value": 0.18, "by": "2026-11-30"},
            "instrumentation": {"event": "workspace.first_export", "exists": False},
        }],
        demand_hypotheses=[{
            "id": "H-1",
            "statement": "admins will adopt one-click bulk export",
            "falsifier": "under 10% of active workspaces use it within 30 days",
            "check": {"stage": "P4", "method": "cohort", "window_days": 30},
        }],
        scope_tier="standard",
        kill_criteria=["O-1 misses 50% of target lift after 2 loops => PL5 review"],
    )
    prd_prose = ("Who: mid-market recruiting ops. Problem: hours lost weekly to "
                 "manual exports, per ticket cluster C-1. Why now: churn interviews.")
    issues, tasks = prd_lint(
        prd, prd_prose, vocabulary=VOCABULARY,
        ledger_claim_ids={"C-1", "C-2"},
    )
    assert issues == []
    assert [t.event for t in tasks] == ["workspace.first_export"]

    # Handoff — emitted, written, and machine-checked at Discovery's DoR.
    handoff = emit_handoff(
        prd, prd_prose, claim_ledger_ref="claims/prd.claim.yaml",
        outcomes_ref="product/outcomes.yaml",
        constraints_inherited=[{"kind": "regulatory", "rule": "no PII in exports",
                                "ref": "C-2"}],
    )
    path = write_handoff(handoff, mas / "handoff" / "p2_to_stage1.yaml")
    accepted = validate_handoff_at_dor(path, prd_document_text=prd_prose)
    assert accepted.prd_ref == "PRD-2026-014"

    # The seed drops straight into Discovery's own validated model — the
    # class mapping of §20.53.6 lands inside Stage 1 without interpretation.
    hypotheses = [
        Hypothesis(statement=h.statement, evidence=h.class_)
        for h in accepted.hypothesis_seed
    ]
    assert hypotheses[0].evidence == "assumed"


# --- malformed handoffs fail at DoR, never get interpreted ----------------------


def _minimal_handoff_dict(prd_text: str = "x") -> dict:
    import hashlib

    return {
        "prd_ref": "PRD-X",
        "prd_hash": "sha256:" + hashlib.sha256(prd_text.encode()).hexdigest(),
        "claim_ledger_ref": "claims/prd.claim.yaml",
        "hypothesis_seed": [
            {"id": "H-1", "statement": "s", "class": "assumed", "falsifier": "f"}
        ],
        "scope_tier": "standard",
        "outcomes_ref": "product/outcomes.yaml",
    }


def _write(tmp_path, doc) -> Path:
    path = tmp_path / "p2_to_stage1.yaml"
    path.write_text(yaml.safe_dump({"handoff": doc}))
    return path


def test_dor_rejects_hash_mismatch(tmp_path):
    path = _write(tmp_path, _minimal_handoff_dict(prd_text="the approved PRD"))
    with pytest.raises(HandoffError, match="prd_hash mismatch"):
        validate_handoff_at_dor(path, prd_document_text="a different PRD")


def test_dor_rejects_bad_class_empty_seed_and_ruleless_constraints(tmp_path):
    doc = _minimal_handoff_dict()
    doc["hypothesis_seed"][0]["class"] = "vibes"
    with pytest.raises(HandoffError, match="Discovery's classes"):
        validate_handoff_at_dor(_write(tmp_path, doc), prd_document_text="x")

    doc = _minimal_handoff_dict()
    doc["hypothesis_seed"] = []
    with pytest.raises(HandoffError, match="closes nothing"):
        validate_handoff_at_dor(_write(tmp_path, doc), prd_document_text="x")

    doc = _minimal_handoff_dict()
    doc["constraints_inherited"] = [{"kind": "regulatory"}]
    with pytest.raises(HandoffError, match="lacks a rule"):
        validate_handoff_at_dor(_write(tmp_path, doc), prd_document_text="x")


def test_dor_rejects_garbage_files(tmp_path):
    path = tmp_path / "p2_to_stage1.yaml"
    path.write_text("just some text")
    with pytest.raises(HandoffError, match="mapping"):
        validate_handoff_at_dor(path, prd_document_text="x")


def test_gate_pl2_carries_the_scope_tier_into_the_build(tmp_path):
    """The tier decided at PL1/PL2 has to reach the planner. handoff.py
    carried it, plan.py read it from project.yaml, and nothing bridged them —
    so a `thin` decided in the outer loop had no effect on any plan (this
    repo's own launch/gate-pl2.yaml says thin)."""
    import shutil

    import pytest
    import yaml as _yaml
    from typer.testing import CliRunner

    if shutil.which("git") is None:
        pytest.skip("git not on PATH")

    from ai_venture_studio.cli import app
    from ai_venture_studio.upstream import init_workspace

    root = init_workspace(tmp_path / "ws", "ws", "web")  # defaults to standard
    (root / "product").mkdir(exist_ok=True)
    prd = {
        "prd": {
            "id": "PRD-1", "problem_statement": "p", "scope_tier": "thin",
            "non_goals": ["a", "b"], "kill_criteria": ["k"],
            "outcomes": [],
            "demand_hypotheses": [{
                "id": "H-1",
                "statement": "founders will use a progress panel",
                "falsifier": "under 30% open it within 30 days",
                "check": {"stage": "P4", "method": "cohort", "window_days": 30},
            }],
            "evidence_refs": [],
        }
    }
    (root / "product" / "prd.yaml").write_text(_yaml.safe_dump(prd))
    (root / "product" / "prd.md").write_text("# PRD\n\nbody\n")

    result = CliRunner().invoke(app, [
        "prd-approve", "--workspace", str(root), "--decider", "melody",
    ])
    assert result.exit_code == 0, result.output
    project = _yaml.safe_load((root / ".mas" / "project.yaml").read_text())
    assert project["scope_tier"] == "thin", "the tier never reached the builder"


def test_a_recorded_test_first_decision_blocks_the_prd(tmp_path):
    """Gate PL1 `test_first` means "do not build yet, run this test" — the
    canon calls it the most common correct outcome. It was a recorded string
    with no downstream wiring: a founder could record it and walk straight
    into a PRD, a handoff, and a build with nothing objecting."""
    import yaml as _yaml
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app

    root = tmp_path / "ws"
    gate_dir = root / ".mas" / "product"
    gate_dir.mkdir(parents=True)
    (gate_dir / "gate-pl1.yaml").write_text(_yaml.safe_dump({
        "outcome": "test_first",
        "named_test": "show 3 reporters a clickable mockup",
        "decider": "melody",
    }))

    result = CliRunner().invoke(app, ["prd", "--workspace", str(root)])
    assert result.exit_code == 3, result.output
    assert "test_first" in result.output
    assert "clickable mockup" in result.output  # the named test is quoted back


def test_a_pursue_decision_does_not_block_the_prd(tmp_path):
    """The gate must only stop the build-first path, not every path."""
    import yaml as _yaml
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app

    root = tmp_path / "ws"
    gate_dir = root / ".mas" / "product"
    gate_dir.mkdir(parents=True)
    (gate_dir / "gate-pl1.yaml").write_text(_yaml.safe_dump({
        "outcome": "pursue", "scope_tier": "thin", "decider": "melody",
    }))
    result = CliRunner().invoke(app, ["prd", "--workspace", str(root)])
    # it proceeds past the tier gate and fails later on missing inputs, which
    # is a different exit code than the test_first refusal
    assert result.exit_code != 3
