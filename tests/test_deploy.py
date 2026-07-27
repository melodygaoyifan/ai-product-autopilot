from pathlib import Path

import yaml

from ai_venture_studio.deploy import DeployVerdict, detect_deploy_files, run_deploy_review
from ai_venture_studio.deploy.probes import migration_scan, workflow_scan
from ai_venture_studio.diff import parse_unified_diff

SKILLS = str(Path(__file__).parent.parent / "skills" / "deploy")


def _diff(path: str, *added: str) -> str:
    body = "\n".join(f"+{line}" for line in added)
    return (
        f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
        f"@@ -1,0 +1,{len(added)} @@\n{body}\n"
    )


def test_detect_deploy_files():
    files = [
        "src/app.py",
        ".github/workflows/deploy.yml",
        "migrations/0042_drop_legacy.py",
        "terraform/prod/main.tf",
        "README.md",
    ]
    assert detect_deploy_files(files) == files[1:4]


def test_migration_scan_flags_drop():
    diff = parse_unified_diff(
        _diff("migrations/0042_cleanup.sql", "DROP TABLE legacy_orders;")
    )
    report = migration_scan(diff, ".")
    assert report.findings[0].severity.value == "critical"
    assert report.findings[0].taxonomy_hint == "deploy:migration"


def test_migration_scan_ignores_non_migration_paths():
    diff = parse_unified_diff(_diff("docs/history.md", "DROP TABLE legacy_orders;"))
    assert migration_scan(diff, ".").findings == []


def test_workflow_scan_flags_write_all_and_fork_trigger():
    diff = parse_unified_diff(
        _diff(
            ".github/workflows/ci.yml",
            "permissions: write-all",
            "on: pull_request_target",
        )
    )
    titles = [f.title for f in workflow_scan(diff, ".").findings]
    assert any("write-all" in t for t in titles)
    assert any("pull_request_target" in t for t in titles)


def test_deploy_review_escalates_destructive_migration(tmp_path):
    result = run_deploy_review(
        "bench://migration",
        repo_dir=str(tmp_path),
        skills_dir=SKILLS,
        provider_override="mock",
        diff_text=_diff("migrations/0099_drop.sql", "DROP TABLE users_backup;"),
    )
    assert result.verdict is DeployVerdict.ESCALATE_MIGRATION_DESTRUCTIVE
    assert result.tier == "insight"


def test_deploy_review_policy_violation_wins(tmp_path):
    # Policy violation outranks migration escalation in §09.11.6 priority.
    result = run_deploy_review(
        "bench://policy",
        repo_dir=str(tmp_path),
        skills_dir=SKILLS,
        provider_override="mock",
        diff_text=_diff(
            ".github/workflows/x.yml",
            "permissions: write-all",
        )
        + _diff("migrations/0100_drop.sql", "DROP TABLE a;"),
    )
    assert result.verdict is DeployVerdict.ESCALATE_POLICY_VIOLATION
    assert any(f.voter == "tool:deploy_policy" for f in result.findings)


def test_deploy_review_clean_change_promotes(tmp_path):
    result = run_deploy_review(
        "bench://clean",
        repo_dir=str(tmp_path),
        skills_dir=SKILLS,
        provider_override="mock",
        diff_text=_diff("helm/values.yaml", "replicaCount: 3"),
    )
    assert result.verdict is DeployVerdict.PROMOTE
    assert "recommendation only" in result.summary
    mirror = sorted(Path(result.artifacts_dir).glob("[0-9]*-*.yaml"))
    assert [p.name.split("-", 1)[1] for p in mirror] == [
        "probes.yaml", "vote.yaml", "final.yaml",
    ]


def test_custom_policy_forbidden_list(tmp_path):
    policy_dir = tmp_path / ".mas"
    policy_dir.mkdir()
    (policy_dir / "deploy-policy.yaml").write_text(
        yaml.safe_dump({"forbidden": ["image: latest"]})
    )
    result = run_deploy_review(
        "bench://custom",
        repo_dir=str(tmp_path),
        skills_dir=SKILLS,
        provider_override="mock",
        diff_text=_diff("k8s/app.yaml", "image: latest"),
    )
    assert result.verdict is DeployVerdict.ESCALATE_POLICY_VIOLATION


# --- lint-only degraded mode (ADR-U15, substrate below S4) ------------------------

def test_lint_only_never_promotes_and_skips_track_record(tmp_path):
    result = run_deploy_review(
        "main...HEAD", repo_dir=str(tmp_path), skills_dir=SKILLS,
        provider_override="mock",
        diff_text=_diff("src/app.py", "print('hello')"),
        lint_only=True,
    )
    if result.verdict is DeployVerdict.PROMOTE:
        raise AssertionError("lint-only ran no voters — it must never PROMOTE")
    if result.verdict is not DeployVerdict.HOLD_FOR_HUMAN:
        raise AssertionError(f"clean lint-only should hold for human: {result.verdict}")
    if "DEGRADED" not in result.summary or "voters did NOT run" not in result.summary:
        raise AssertionError(f"summary must say degraded loudly: {result.summary}")
    track = tmp_path / ".mas" / "deploy-track-record.yaml"
    if track.exists():
        raise AssertionError("lint-only runs must not feed the promotion track record")
    vote_steps = list((tmp_path / ".mas" / "deploy-reviews").glob("*/[0-9][0-9]-vote.yaml"))
    vote = yaml.safe_load(vote_steps[0].read_text(encoding="utf-8"))
    if "lint_only" not in str(vote.get("skipped", "")):
        raise AssertionError(f"mirror must record the skipped voters: {vote}")


def test_lint_only_still_escalates_deterministic_findings(tmp_path):
    result = run_deploy_review(
        "main...HEAD", repo_dir=str(tmp_path), skills_dir=SKILLS,
        provider_override="mock",
        diff_text=_diff(".github/workflows/ci.yml", "    permissions: write-all"),
        lint_only=True,
    )
    if result.verdict is not DeployVerdict.ESCALATE_POLICY_VIOLATION:
        raise AssertionError(
            f"the deterministic policy scan must still escalate: {result.verdict}"
        )
