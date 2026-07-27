"""The four product-loop stages as one-command stages, hermetic on the
mock provider: writer → det tools → voters → verify → leader → gate, and
the full P0→P1→PL1→P2→PL2(handoff)→P4 chain in one workspace.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from ai_venture_studio.cli import app
from ai_venture_studio.product.stage_engine import load_voter_charters, run_product_stage
from ai_venture_studio.product.stages import market_spec, opportunity_spec

REPO_METRICS = str(Path(__file__).parent.parent / "metrics")
runner = CliRunner()


def _workspace(tmp_path: Path) -> Path:
    mas = tmp_path / ".mas"
    mas.mkdir()
    (mas / "signal-sources.yaml").write_text(
        "- id: support-tickets\n  standing: first-party, ours\n"
        "  match: ['evidence://']\n"
        "- id: crm\n  standing: first-party, ours\n  match: ['crm://']\n"
    )
    (tmp_path / "signals.yaml").write_text(yaml.safe_dump([
        {"id": "s1", "source_id": "support-tickets",
         "text": "Bulk export to CSV takes forever from the reports page"},
        {"id": "s2", "source_id": "support-tickets",
         "text": "Bulk export to CSV takes forever from the reports page today"},
        {"id": "s3", "source_id": "support-tickets",
         "text": "Would love a dark mode for late night reviews"},
    ]))
    return tmp_path


def test_voter_charters_load_for_every_stage():
    for stage, expected in (("opportunity", 5), ("market", 6),
                            ("prd", 5), ("evidence", 5), ("prioritization", 3)):
        charters = load_voter_charters(stage)
        assert len(charters) == expected, stage
        for name, system in charters:
            assert "PRODUCT-STAGE VOTER" in system and name


def test_opportunity_stage_end_to_end(tmp_path):
    ws = _workspace(tmp_path)
    result = runner.invoke(app, [
        "opportunity", str(ws / "signals.yaml"),
        "--workspace", str(ws), "--provider", "mock",
    ])
    assert result.exit_code == 0, result.output
    assert "opportunity: ok" in result.output
    assert (ws / "product" / "opportunities.md").exists()
    ledger = yaml.safe_load((ws / "claims" / "opportunity.claim.yaml").read_text())
    assert len(ledger["claims"]) == 3
    report = yaml.safe_load(
        (ws / ".mas" / "product" / "opportunity-report.yaml").read_text()
    )
    assert report["gate"]["passed"] and len(report["gate"]["ranked"]) == 3
    assert report["voter_findings"]  # five seats voted; verified minors recorded
    assert {f["voter"] for f in report["voter_findings"]} == {
        "signal_strength", "novelty", "fit", "falsifiability", "duplication"
    }


def test_undeclared_signal_source_fails_closed(tmp_path):
    ws = _workspace(tmp_path)
    (ws / "signals.yaml").write_text(yaml.safe_dump([
        {"id": "s1", "source_id": "scraped-forum", "text": "whatever"},
    ]))
    result = runner.invoke(app, [
        "opportunity", str(ws / "signals.yaml"),
        "--workspace", str(ws), "--provider", "mock",
    ])
    assert result.exit_code == 2
    assert "no standing, no source" in " ".join(result.output.split())


def test_market_stage_gate_blocks_until_the_human_work_is_done(tmp_path):
    ws = _workspace(tmp_path)
    blocked = runner.invoke(app, [
        "market", "cand-a", "--workspace", str(ws), "--provider", "mock",
    ])
    assert blocked.exit_code == 1
    assert "disconfirmation" in blocked.output.lower()
    # Artifacts still land — the gate blocks release, not the work.
    assert (ws / "market" / "sizing.yaml").exists()

    ok = runner.invoke(app, [
        "market", "cand-a", "--workspace", str(ws), "--provider", "mock",
        "--disconfirmation-answered", "--regulatory-triaged",
    ])
    assert ok.exit_code == 0, ok.output
    sizing = yaml.safe_load((ws / "market" / "sizing.yaml").read_text())
    assert sizing["status"] == "ok" and sizing["result_range"]


def test_direct_engine_run_reports_verified_findings(tmp_path):
    ws = _workspace(tmp_path)
    report = run_product_stage(
        market_spec(str(ws), disconfirmation_answered=True, regulatory_triaged=True),
        "<candidate>cand-a</candidate>", str(ws), provider="mock",
    )
    assert report.status == "ok"
    assert all(f.verified for f in report.voter_findings)
    assert "disconfirmation" in {f.voter for f in report.voter_findings}


def test_full_chain_p0_to_p4(tmp_path):
    ws = _workspace(tmp_path)
    assert runner.invoke(app, [
        "opportunity", str(ws / "signals.yaml"),
        "--workspace", str(ws), "--provider", "mock",
    ]).exit_code == 0
    assert runner.invoke(app, [
        "market", "cand-a", "--workspace", str(ws), "--provider", "mock",
        "--disconfirmation-answered", "--regulatory-triaged",
    ]).exit_code == 0
    approve = runner.invoke(app, [
        "market-approve", "--outcome", "pursue", "--decider", "melody",
        "--scope-tier", "standard", "--workspace", str(ws),
    ])
    assert approve.exit_code == 0 and "Gate PL1 recorded" in approve.output

    prd = runner.invoke(app, [
        "prd", "--workspace", str(ws), "--provider", "mock",
        "--metrics-dir", REPO_METRICS,
    ])
    assert prd.exit_code == 0, prd.output
    tasks = yaml.safe_load((ws / "product" / "planning-tasks.yaml").read_text())
    assert tasks["tasks"][0]["event"] == "workspace.first_export"

    approved = runner.invoke(app, [
        "prd-approve", "--decider", "melody", "--workspace", str(ws),
    ])
    assert approved.exit_code == 0, approved.output
    assert "validated at Discovery's DoR" in " ".join(approved.output.split())
    assert (ws / "handoff" / "p2_to_stage1.yaml").exists()

    events = [
        {"unit": f"u{i}", "signup_week": "w1", "event": "workspace.created"}
        for i in range(250)
    ] + [
        {"unit": f"u{i}", "signup_week": "w1", "event": "workspace.first_export"}
        for i in range(32)
    ]
    (ws / "events.yaml").write_text(yaml.safe_dump(events))
    evidence = runner.invoke(app, [
        "evidence", str(ws / "events.yaml"), "--workspace", str(ws),
        "--provider", "mock", "--metrics-dir", REPO_METRICS,
        "--cohort-start", "2026-07-01",
    ])
    assert evidence.exit_code == 0, evidence.output
    verdicts = yaml.safe_load((ws / "evidence" / "verdicts.yaml").read_text())
    assert verdicts["verdicts"][0]["verdict"] == "not_supported"  # 12.8% vs 18%
    assert verdicts["readings"]["O-1"]["value"] == 0.128

    # The reports of all four stages exist — the loop's paper trail.
    for stage in ("opportunity", "market", "prd", "evidence"):
        assert (ws / ".mas" / "product" / f"{stage}-report.yaml").exists()


def test_prd_voters_see_the_generated_planning_tasks(tmp_path):
    from ai_venture_studio.product.stages import prd_spec

    ws = _workspace(tmp_path)
    spec = prd_spec(str(ws), metrics_dir=REPO_METRICS,
                    ledger_claim_ids={"C-M1", "C-M2"})
    import ai_venture_studio.providers.mock as mock_mod
    from ai_venture_studio.yamlx import extract_mapping

    data = extract_mapping(mock_mod.MockProvider()._prd_writer(), ("prd",))
    bundle, artifact_text = spec.parse(data)
    assert spec.det_tools(bundle) == []  # generates the task, no findings
    context = spec.voter_context(bundle, artifact_text)
    assert "generated_planning_tasks" in context
    assert "workspace.first_export" in context
    assert "instrumented-or-tasked" in context


def test_gate_pl0_blocks_a_thin_candidate_set(tmp_path, monkeypatch):
    ws = _workspace(tmp_path)
    import ai_venture_studio.providers.mock as mock_mod

    thin = yaml.safe_dump({"candidates": yaml.safe_load(
        mock_mod.MockProvider()._opportunity_writer()
    )["candidates"][:1]}, sort_keys=False)
    monkeypatch.setattr(
        mock_mod.MockProvider, "_opportunity_writer", lambda self: thin
    )
    report = run_product_stage(
        opportunity_spec(str(ws)),
        "clusters: []", str(ws), provider="mock",
    )
    assert report.status == "gate_blocked"
    assert any(
        f["rule"] == "insufficient_candidates" for f in report.gate["findings"]
    )
