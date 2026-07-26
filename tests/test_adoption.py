"""Adoption track (docs 18-19, G1-G2): substrate ladder, readiness report,
Gate R preflight, evidence bundle. All hermetic — tmp_path workspaces only."""

from pathlib import Path

import pytest
import yaml

from autoproduct.adoption import (
    ChangePackage,
    Rung,
    StageInactiveError,
    StageStatus,
    SubstrateProfile,
    build_evidence_bundle,
    check_stage,
    gate_r_entry,
    load_preflight_checklist,
    load_substrate_profile,
    readiness_report,
    record_rejection,
    rung_banner,
    stage_activation,
    write_evidence_bundle,
)
from autoproduct.adoption.substrate import PROFILE_FILENAME


def _write_profile(root: Path, substrate: dict) -> Path:
    path = root / PROFILE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"substrate": substrate}), encoding="utf-8")
    return path


S0 = {"vcs": "none"}
S1 = {"vcs": "git", "pr_flow": True}
S2 = {**S1, "ci": True}
S3 = {**S2, "observability": ["sentry"]}
S4 = {**S3, "progressive_delivery": True}


# --- profile loading + rung computation --------------------------------------

def test_rung_boundaries():
    expected = [(S0, Rung.S0), (S1, Rung.S1), (S2, Rung.S2), (S3, Rung.S3), (S4, Rung.S4)]
    for substrate, rung in expected:
        if SubstrateProfile(**substrate).rung() != rung:
            pytest.fail(f"{substrate} should compute {rung.label}")


def test_git_without_pr_flow_is_still_s0():
    # PR flow, not bare git, is what Code Review needs.
    if SubstrateProfile(vcs="git").rung() != Rung.S0:
        pytest.fail("git without pr_flow must stay S0")


def test_pr_flow_without_git_rejected():
    with pytest.raises(ValueError, match="requires vcs: git"):
        SubstrateProfile(vcs="none", pr_flow=True)


def test_progressive_delivery_without_ci_rejected():
    with pytest.raises(ValueError, match="requires ci"):
        SubstrateProfile(vcs="git", pr_flow=True, progressive_delivery=True)


def test_unknown_observability_named_in_error():
    with pytest.raises(ValueError, match="splunk"):
        SubstrateProfile(vcs="git", observability=["splunk"])


def test_missing_file_means_no_gating(tmp_path):
    if load_substrate_profile(tmp_path) is not None:
        pytest.fail("absent profile must return None (ladder is opt-in)")
    if check_stage(tmp_path, "code_review") is not None:
        pytest.fail("check_stage must no-op without a profile")


def test_malformed_profile_is_a_useful_hard_error(tmp_path):
    path = tmp_path / PROFILE_FILENAME
    path.parent.mkdir(parents=True)
    path.write_text("substrate: {vcs: svn}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="vcs"):
        load_substrate_profile(tmp_path)


def test_missing_top_level_key_rejected(tmp_path):
    path = tmp_path / PROFILE_FILENAME
    path.parent.mkdir(parents=True)
    path.write_text("vcs: git\n", encoding="utf-8")
    with pytest.raises(ValueError, match="substrate"):
        load_substrate_profile(tmp_path)


# --- stage activation ---------------------------------------------------------

def test_s0_routes_spec_and_refuses_code_review(tmp_path):
    _write_profile(tmp_path, S0)
    if check_stage(tmp_path, "specification").status is not StageStatus.ACTIVE:
        pytest.fail("specification must be active at S0 (the wedge)")
    with pytest.raises(StageInactiveError) as exc_info:
        check_stage(tmp_path, "code_review")
    act = exc_info.value.activation
    if (act.rung_required, act.rung_present) != ("S1", "S0"):
        pytest.fail(f"structured notice wrong: {act}")
    if "git + PR flow" not in act.note:
        pytest.fail("notice must name what is missing")


def test_deploy_review_degraded_not_inactive_at_s1():
    act = stage_activation(SubstrateProfile(**S1), "deploy_review")
    if act.status is not StageStatus.DEGRADED:
        pytest.fail("deploy_review at S1 is the named lint-only exception")
    if "lint" not in act.note:
        pytest.fail("degraded banner must say lint-only")


def test_deploy_review_inactive_at_s0():
    act = stage_activation(SubstrateProfile(**S0), "deploy_review")
    if act.status is not StageStatus.STAGE_INACTIVE:
        pytest.fail("no repo, nothing to lint — inactive at S0")


def test_unknown_stage_rejected():
    with pytest.raises(ValueError, match="unknown stage"):
        stage_activation(SubstrateProfile(**S4), "shipping")


def test_banner_carries_rung_and_inactive_stages():
    banner = rung_banner(SubstrateProfile(**S0))
    if "S0" not in banner or "code_review" not in banner:
        pytest.fail(f"F-18.5: banner must expose the wedge: {banner}")
    if "inactive" in rung_banner(SubstrateProfile(**S4)):
        pytest.fail("S4 banner must not list inactive stages")


# --- readiness report ---------------------------------------------------------

def test_readiness_report_reads_as_roadmap():
    report = readiness_report(SubstrateProfile(**S1), project_name="pilot")
    for expected in ("S1", "code_review | active", "test | inactive",
                     "CI (machine-runnable", "unlocks: test"):
        if expected not in report:
            pytest.fail(f"report missing {expected!r}:\n{report}")


def test_readiness_report_all_rungs_met():
    report = readiness_report(SubstrateProfile(**S4))
    if "All rungs met" not in report:
        pytest.fail(report)


# --- Gate R -------------------------------------------------------------------

def _complete_package(tmp_path: Path) -> ChangePackage:
    bundle = tmp_path / "bundle.md"
    bundle.write_text("# evidence\n", encoding="utf-8")
    return ChangePackage(
        change_id="CHG-1",
        description="rotate the widget",
        rollback_plan="revert the transport",
        affected_systems=["wms"],
        evidence_bundle=str(bundle),
        approver_role="change-manager",
        required_role="change-manager",
    )


def test_gate_r_green_on_complete_package(tmp_path):
    entry = gate_r_entry(tmp_path, _complete_package(tmp_path))
    if not entry.eligible:
        pytest.fail(f"complete package must be eligible: {entry.failures}")


def test_gate_r_names_each_failure(tmp_path):
    package = _complete_package(tmp_path)
    package.rollback_plan = ""
    package.approver_role = "developer"
    entry = gate_r_entry(tmp_path, package)
    failed_ids = {r.check.id for r in entry.failures}
    if failed_ids != {"rollback_plan", "approver_role"}:
        pytest.fail(f"unexpected failures: {failed_ids}")
    if entry.eligible:
        pytest.fail("must not be eligible with failures")


def test_gate_r_missing_evidence_bundle_fails(tmp_path):
    package = _complete_package(tmp_path)
    package.evidence_bundle = "does/not/exist.md"
    entry = gate_r_entry(tmp_path, package)
    if "evidence_bundle" not in {r.check.id for r in entry.failures}:
        pytest.fail("unreadable bundle must fail preflight")


def test_rejection_reasons_split_fixture_vs_loop(tmp_path):
    counts = record_rejection(
        tmp_path,
        "CHG-2",
        [
            {"reason": "privacy string missing from manifest", "mechanizable": True},
            {"reason": "business justification unconvincing", "mechanizable": False},
        ],
    )
    if counts != {"preflight_fixtures": 1, "compounding_entries": 1}:
        pytest.fail(f"split wrong: {counts}")
    checks = load_preflight_checklist(tmp_path)
    sourced = [c for c in checks if c.source == "rejection:CHG-2"]
    if len(sourced) != 1 or "privacy string" not in sourced[0].description:
        pytest.fail("mechanizable reason must become a preflight fixture")
    log = yaml.safe_load((tmp_path / ".mas/cab-rejections.yaml").read_text())
    if len(log["rejections"]) != 1:
        pytest.fail("non-mechanizable reason must land in the rejections log")


def test_rejection_fixture_requires_manual_attestation(tmp_path):
    record_rejection(
        tmp_path, "CHG-3", [{"reason": "screenshots stale", "mechanizable": True}]
    )
    entry = gate_r_entry(tmp_path, _complete_package(tmp_path))
    fixture_results = [r for r in entry.results if r.check.id.startswith("rej_")]
    if fixture_results[0].passed:
        pytest.fail("rejection-sourced checks fail until attested/mechanized")


def test_empty_rejection_reason_rejected(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        record_rejection(tmp_path, "CHG-4", [{"reason": "  ", "mechanizable": True}])


# --- evidence bundle ----------------------------------------------------------

def _fake_mirror(tmp_path: Path, review_id: str) -> Path:
    review_dir = tmp_path / ".mas" / "reviews" / review_id
    review_dir.mkdir(parents=True)
    steps = [
        ("01-dor_gate.yaml", {"node": "dor_gate", "step": 1,
                              "written_at": "2026-07-25T00:00:00+00:00", "dor_pass": True}),
        ("02-voters.yaml", {"node": "voters", "step": 2,
                            "written_at": "2026-07-25T00:01:00+00:00", "count": 6}),
        ("03-leader.yaml", {"node": "leader", "step": 3,
                            "written_at": "2026-07-25T00:02:00+00:00",
                            "verdict": "REQUEST_CHANGES"}),
        ("04-hitl.yaml", {"node": "hitl", "step": 4,
                          "written_at": "2026-07-25T00:03:00+00:00",
                          "decision": "ack", "resumed_by": "reviewer"}),
    ]
    for name, payload in steps:
        (review_dir / name).write_text(yaml.safe_dump(payload), encoding="utf-8")
    return review_dir


def test_bundle_contains_gates_and_verdicts(tmp_path):
    _fake_mirror(tmp_path, "rev-1")
    bundle = build_evidence_bundle(tmp_path, "rev-1")
    for expected in ("verdict=REQUEST_CHANGES", "decision=ack", "dor_pass=True",
                     "unsigned", "Steps recorded: 4"):
        if expected not in bundle:
            pytest.fail(f"bundle missing {expected!r}:\n{bundle}")
    # step 02 has no gate/verdict state and must not appear as attested
    if "`voters`" in bundle.split("## Full step index")[0]:
        pytest.fail("non-attestable step leaked into the gate section")


def test_bundle_refuses_missing_review(tmp_path):
    with pytest.raises(FileNotFoundError, match="nothing to attest"):
        build_evidence_bundle(tmp_path, "rev-none")


def test_bundle_with_no_gate_state_says_so(tmp_path):
    review_dir = tmp_path / ".mas" / "reviews" / "rev-2"
    review_dir.mkdir(parents=True)
    (review_dir / "01-voters.yaml").write_text(
        yaml.safe_dump({"node": "voters", "step": 1, "count": 2}), encoding="utf-8"
    )
    bundle = build_evidence_bundle(tmp_path, "rev-2")
    if "NOT submission evidence" not in bundle:
        pytest.fail("a trail without gate state must be labeled non-evidence")


def test_write_bundle_lands_in_evidence_dir(tmp_path):
    _fake_mirror(tmp_path, "rev-3")
    path = write_evidence_bundle(tmp_path, "rev-3")
    if path != tmp_path / ".mas" / "evidence" / "rev-3.md" or not path.exists():
        pytest.fail(f"unexpected bundle path: {path}")


# --- CLI guard (F-18.1 adjacent: the refusal is loud, coded, and routed) ------

def test_review_cli_exits_4_below_floor(tmp_path):
    from typer.testing import CliRunner

    from autoproduct.cli import app

    _write_profile(tmp_path, S0)
    result = CliRunner().invoke(
        app, ["review", "main...HEAD", "--repo-dir", str(tmp_path)]
    )
    if result.exit_code != 4:
        pytest.fail(f"expected exit 4, got {result.exit_code}: {result.output}")
    if "STAGE_INACTIVE" not in result.output or "readiness" not in result.output:
        pytest.fail(f"refusal must be structured and route to readiness: {result.output}")
