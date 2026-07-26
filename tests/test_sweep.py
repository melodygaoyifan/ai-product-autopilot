"""The Sweep role (doc 29): harvested queues, the behavior-preservation
contract (invariant 14.29), attention caps + recorded clean passes
(invariant 14.30), the SW ladder, and the over-action alarm."""

from __future__ import annotations

import datetime as dt

import pytest
import yaml
from typer.testing import CliRunner

from autoproduct.cli import app
from autoproduct.lanes.delivery import flag_lint
from autoproduct.sweep import (
    ContractCheck,
    SweepConfig,
    SweepConfigError,
    behavior_preservation_check,
    harvest_queues,
    load_sweep_config,
    over_action_alarm,
    run_sweep_pass,
)

TODAY = dt.date(2026, 7, 26)
runner = CliRunner()

FLAGS = (
    "flags:\n"
    "  - {name: old-toggle, category: release, owner: melody,\n"
    "     created: '2026-04-01', expiry: '2026-05-01',\n"
    "     final_state: 'on', removal_trigger: '30d at 100%'}\n")

CONTRIBUTING = (
    "| Item | Review by | What would change our mind |\n|---|---|---|\n"
    "| Agent Skills spec convergence | 2026-07-01 | spec stabilizes |\n"
    "| MCP Server Cards | 2026-10-01 | adoption lands |\n")


def _chores():
    return harvest_queues(
        ".", today=TODAY,
        flag_issues=flag_lint(FLAGS, {}, today=TODAY),
        checkpoint_debt=7,
        stale_claims=["C-9"],
        stale_capacity=["POST /api/orders"],
        contract_drift=[{"topic": "orders", "message": "mode drift"}],
        contributing_text=CONTRIBUTING,
    )


def test_harvest_unions_the_existing_ledgers():
    chores = _chores()
    queues = {c.queue for c in chores}
    assert queues == {"flags", "deprecated_references", "claim_ledger",
                      "capacity", "stream_contracts", "watch_items"}
    # only the DUE watch item is harvested
    watch = [c for c in chores if c.queue == "watch_items"]
    assert [c.item for c in watch] == ["Agent Skills spec convergence"]
    assert chores[0].chore_class == "flag_removal"  # expired-blocking ranks first


def test_sw0_is_report_only_and_clean_pass_is_recorded(tmp_path):
    digest = run_sweep_pass(tmp_path, _chores(), config=SweepConfig(), at="2026-07-26")
    assert digest.rung == "SW0" and digest.actionable == []
    assert digest.action_rate == 0.0 and not digest.clean_pass

    clean = run_sweep_pass(tmp_path, [], config=SweepConfig(), at="2026-07-27")
    assert clean.clean_pass and clean.snapshot_hash.startswith("sha256:")
    assert (tmp_path / ".mas" / "sweep" / "digest-2026-07-27.yaml").exists()


def test_sw1_patches_flag_removals_within_the_cap(tmp_path):
    config = SweepConfig(rung="SW1", enabled_classes=["flag_removal"],
                         max_open_prs=1, promoted_by="melody")
    digest = run_sweep_pass(tmp_path, _chores(), config=config, at="2026-07-26")
    assert [c.chore_class for c in digest.actionable] == ["flag_removal"]
    assert len(digest.actionable) == 1  # E2 cap honored (invariant 14.30)
    assert len(digest.reported) == len(digest.chores) - 1


def test_config_guards():
    assert load_sweep_config("/nonexistent").rung == "SW0"
    with pytest.raises(SweepConfigError, match="allowlist"):
        SweepConfig(rung="SW2", enabled_classes=["rewrite_specs"],
                    promoted_by="x"); _reload("rewrite_specs")
    with pytest.raises(SweepConfigError, match="report-only"):
        _reload_cfg({"rung": "SW0", "enabled_classes": ["flag_removal"]})
    with pytest.raises(SweepConfigError, match="human decision"):
        _reload_cfg({"rung": "SW1", "enabled_classes": ["flag_removal"]})


def _reload(cls):  # helper: run the loader path for allowlist enforcement
    _reload_cfg({"rung": "SW2", "enabled_classes": [cls], "promoted_by": "x"})


def _reload_cfg(raw):
    import pathlib
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "sweep.yaml"
        path.write_text(yaml.safe_dump(raw))
        load_sweep_config(tmp)


def test_behavior_preservation_contract():
    good = ContractCheck(
        chore_class="flag_removal",
        files_touched=["src/app/flags.py", ".mas/flags.yaml"],
        declared_scope=["src/app/flags.py", ".mas/flags.yaml"],
        suite_green=True, coverage_delta=0.0,
        api_surface_unchanged=True, baselines_untouched=True)
    assert behavior_preservation_check(good) == []

    bad = good.model_copy(update={
        "files_touched": ["src/app/flags.py", "src/app/pricing.py"],
        "coverage_delta": -0.01, "api_surface_unchanged": False})
    failures = behavior_preservation_check(bad)
    assert any("outside declared scope" in f for f in failures)
    assert any("coverage decreased" in f for f in failures)
    assert any("api_surface" in f for f in failures)
    assert behavior_preservation_check(
        good.model_copy(update={"chore_class": "refactor_everything"}))


def test_over_action_alarm(tmp_path):
    quiet = run_sweep_pass(tmp_path, _chores(),
                           config=SweepConfig(), at="2026-07-19")
    busy = run_sweep_pass(
        tmp_path, _chores(),
        config=SweepConfig(rung="SW2", enabled_classes=list(
            {"flag_removal", "ledger_reconciliation"}), max_open_prs=2,
            promoted_by="melody"),
        at="2026-07-26")
    assert over_action_alarm(quiet, busy, debt_delta=0)  # churn, flat debt
    assert not over_action_alarm(quiet, busy, debt_delta=-4)  # real cleaning


def test_sweep_cli_end_to_end(tmp_path):
    (tmp_path / ".mas").mkdir()
    (tmp_path / ".mas" / "flags.yaml").write_text(FLAGS)
    (tmp_path / "CONTRIBUTING.md").write_text(CONTRIBUTING)
    result = runner.invoke(app, ["sweep", "--workspace", str(tmp_path),
                                 "--today", "2026-07-26"])
    assert result.exit_code == 0, result.output
    out = " ".join(result.output.split())
    assert "sweep SW0" in out and "0 actionable" in out
    digest = yaml.safe_load(
        (tmp_path / ".mas" / "sweep" / "digest-2026-07-26.yaml").read_text())
    assert digest["items_inspected"] >= 2  # expired flag + due watch item
