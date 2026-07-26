"""The product-loop CLI surface: prd-lint, handoff-check, experiment-check,
preregister — each gate runnable standalone, exit codes per the claim-lint
contract (0 clean / 1 findings / 2 malformed).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from autoproduct.cli import app
from autoproduct.experiment import lock_preregistration
from autoproduct.product import PRD, emit_handoff, write_handoff

REPO_METRICS = str(Path(__file__).parent.parent / "metrics")

runner = CliRunner()


def _prd_dict() -> dict:
    return {
        "id": "PRD-2026-014",
        "problem_statement": "Recruiting ops teams lose hours weekly to manual exports.",
        "evidence_refs": ["C-1"],
        "non_goals": ["No custom report builder.", "No new segment."],
        "outcomes": [{
            "id": "O-1",
            "metric": "activation_rate",
            "definition_ref": "metrics/activation_rate.md",
            "target": {"value": 0.18, "by": "2026-11-30"},
            "instrumentation": {"event": "workspace.first_export", "exists": True},
        }],
        "demand_hypotheses": [{
            "id": "H-1", "statement": "admins adopt bulk export",
            "falsifier": "under 10% adoption in 30 days",
        }],
        "scope_tier": "standard",
        "kill_criteria": ["O-1 misses 50% of target lift after 2 loops"],
    }


def test_prd_lint_cli(tmp_path):
    prd_path = tmp_path / "prd.yaml"
    prd_path.write_text(yaml.safe_dump({"prd": _prd_dict()}))
    prose = tmp_path / "prd.md"
    prose.write_text("Who: recruiting ops. Problem: manual export hours. Why now: churn.")
    result = runner.invoke(
        app, ["prd-lint", str(prd_path), "--prose", str(prose),
              "--metrics-dir", REPO_METRICS],
    )
    assert result.exit_code == 0, result.output

    prose.write_text("When an admin clicks export, the system shall emit a CSV.")
    result = runner.invoke(
        app, ["prd-lint", str(prd_path), "--prose", str(prose),
              "--metrics-dir", REPO_METRICS],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout.splitlines()[0])["rule"] == "ears_leakage"

    prd_path.write_text("not: a prd")
    result = runner.invoke(
        app, ["prd-lint", str(prd_path), "--prose", str(prose),
              "--metrics-dir", REPO_METRICS],
    )
    assert result.exit_code == 2


def test_handoff_check_cli(tmp_path):
    prd = PRD(**_prd_dict())
    prd_doc = tmp_path / "prd.md"
    prd_doc.write_text("the approved PRD prose")
    handoff = emit_handoff(
        prd, prd_doc.read_text(),
        claim_ledger_ref="claims/prd.claim.yaml", outcomes_ref="product/outcomes.yaml",
    )
    path = write_handoff(handoff, tmp_path / "p2_to_stage1.yaml")
    result = runner.invoke(
        app, ["handoff-check", str(path), "--prd-document", str(prd_doc)]
    )
    assert result.exit_code == 0, result.output
    assert "handoff ok" in result.output

    prd_doc.write_text("a silently edited PRD")
    result = runner.invoke(
        app, ["handoff-check", str(path), "--prd-document", str(prd_doc)]
    )
    assert result.exit_code == 2
    assert "prd_hash mismatch" in result.output


DESIGN = """\
experiment:
  id: EXP-2026-031
  hypothesis: "Outcome-led headline raises signup-start rate"
  primary_metric: signup_start_rate
  design:
    stage1: {arms: 3, correction: benjamini_hochberg, q: 0.10}
    stage2: {arms: 2, fresh_sample: true}
  power: {baseline: 0.06, mde_relative: 0.5, alpha: 0.05, power: 0.80}
  monitoring: {method: sequential, spending: obrien_fleming, peeks: 4}
  stopping_rule: "Horizon or boundary."
  decision_rule: "Adopt only if stage2 significant and guardrails hold."
  preregistration_hash: ""
"""


def test_experiment_check_and_preregister_cli(tmp_path):
    path = tmp_path / "exp.yaml"
    path.write_text(DESIGN)

    pin = runner.invoke(app, ["preregister", str(path)]).stdout.strip()
    assert pin == lock_preregistration(DESIGN)
    path.write_text(DESIGN.replace('preregistration_hash: ""',
                                   f"preregistration_hash: {pin}"))

    result = runner.invoke(
        app, ["experiment-check", str(path), "--weekly-traffic", "20000"]
    )
    assert result.exit_code == 0, result.output
    assert "design ok" in result.output

    result = runner.invoke(
        app, ["experiment-check", str(path), "--weekly-traffic", "150",
              "--max-days", "23"],
    )
    assert result.exit_code == 1
    assert "BLOCKED(INSUFFICIENT_POWER)" in result.stdout

    tampered = path.read_text().replace("mde_relative: 0.5", "mde_relative: 0.3")
    path.write_text(tampered)
    result = runner.invoke(
        app, ["experiment-check", str(path), "--weekly-traffic", "20000"]
    )
    assert result.exit_code == 1
    assert any(
        json.loads(line).get("rule") == "preregistration_mismatch"
        for line in result.stdout.splitlines()
        if line.startswith("{")
    )
