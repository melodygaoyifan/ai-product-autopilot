import shutil

import pytest

from ai_venture_studio import testing as testing_mod
from ai_venture_studio.upstream import (
    approve_spec,
    init_workspace,
    load_project,
    run_build,
    run_spec_stage,
)
from ai_venture_studio.upstream.ears import classify, lint_criteria

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)


# --- ears_lint ---------------------------------------------------------------

def test_ears_patterns_accepted():
    good = [
        "The system shall store items in memory.",
        "When a client POSTs /items, the system shall return the new id.",
        "While offline, the app shall queue writes locally.",
        "If the name is empty, then the system shall reject the request.",
        "Where subpackages are enabled, the app shall lazy-load them.",
    ]
    assert lint_criteria(good) == []
    assert classify(good[1]) == "event"


def test_ears_rejects_non_pattern_and_vague():
    issues = lint_criteria(["Items can be added quickly.", "The app shall be fast."])
    problems = " | ".join(i.problem for i in issues)
    assert "does not match any EARS pattern" in problems
    assert "vague term" in problems


# --- workspace ---------------------------------------------------------------

def test_init_workspace_seeds_profile_constraints(tmp_path):
    root = init_workspace(tmp_path / "shop", "shop", "miniprogram")
    project = load_project(root)
    assert project.profile == "miniprogram"
    claude = (root / "CLAUDE.md").read_text()
    assert "2MB" in claude and "隐私协议" in claude
    with pytest.raises(FileExistsError):
        init_workspace(root, "shop", "miniprogram")


def test_unknown_profile_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown profile"):
        init_workspace(tmp_path / "x", "x", "desktop")


# --- spec stage --------------------------------------------------------------

def test_spec_stage_produces_approvable_spec(tmp_path):
    root = init_workspace(tmp_path / "web", "web", "web")
    spec = run_spec_stage(root, "an item store API", provider="mock")
    assert spec.status == "proposed"
    assert spec.revisions == 0
    assert lint_criteria(spec.criteria) == []
    assert (root / "specs" / spec.slug / "spec.md").exists()


def test_spec_stage_revises_vague_first_draft(tmp_path):
    root = init_workspace(tmp_path / "web", "web", "web")
    spec = run_spec_stage(root, "an item store API, make it vague", provider="mock")
    # First draft had "shall be fast"; lint + critic majors forced a revision.
    assert spec.revisions >= 1
    assert spec.status == "proposed"
    assert all("fast" not in c for c in spec.criteria)


def test_build_refuses_unapproved_spec(tmp_path):
    root = init_workspace(tmp_path / "web", "web", "web")
    spec = run_spec_stage(root, "an item store API", provider="mock")
    result = run_build(root, spec.slug, provider="mock")
    assert result.status == "error"
    assert "Gate U3" in result.detail


# --- full greenfield flow ----------------------------------------------------

def test_end_to_end_init_spec_approve_build(tmp_path, monkeypatch):
    monkeypatch.setattr(testing_mod, "docker_available", lambda: False)
    import ai_venture_studio.upstream.build as build_mod

    monkeypatch.setattr(build_mod, "docker_available", lambda: False)

    root = init_workspace(tmp_path / "web", "web", "web")
    spec = run_spec_stage(root, "an item store API", provider="mock")
    approve_spec(root, spec.slug)

    result = run_build(root, spec.slug, provider="mock")
    assert result.status == "built", result.detail
    assert result.commit
    assert "feature.py" in result.files_written
    assert (root / "tests" / "test_feature.py").exists()
    assert "2 passed" in result.test_summary

    # The build commit is a reviewable diff for the downstream stages.
    from ai_venture_studio.orchestrator import run_review
    from pathlib import Path

    skills = str(Path(__file__).parent.parent / "skills")
    review, state = run_review(
        "HEAD~1", repo_dir=str(root), skills_dir=skills, provider_override="mock"
    )
    assert review is not None
    assert state["dor_pass"]


# --- brownfield safety: init must not destroy an existing CLAUDE.md ----------


def test_init_appends_to_an_existing_claude_md_instead_of_clobbering_it(tmp_path):
    """CLAUDE.md is the operator's own constraints file and every spec,
    build, and review reads it. init used to write_text over it
    unconditionally, which silently destroyed context nothing else can
    reconstruct — the first thing a brownfield adopter would lose."""
    from ai_venture_studio.upstream import init_workspace

    root = tmp_path / "existing"
    root.mkdir()
    hand_written = (
        "# Payments service\n\n"
        "## House rules\n\n"
        "- never log a card number\n"
        "- all money is integer cents\n"
    )
    (root / "CLAUDE.md").write_text(hand_written, encoding="utf-8")

    init_workspace(root, "existing", "web")

    after = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "never log a card number" in after, "hand-written constraints lost"
    assert "all money is integer cents" in after
    assert after.startswith("# Payments service")  # their doc, still theirs
    assert "## avs profile: web" in after  # profile appended, not merged in


def test_init_still_writes_claude_md_when_there_is_none(tmp_path):
    from ai_venture_studio.upstream import init_workspace

    root = init_workspace(tmp_path / "fresh", "fresh", "web")
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith("# fresh — project constraints")
    assert "Domain profile: **web**" in text


def test_appending_the_profile_section_is_idempotent(tmp_path):
    """Re-initializing after a .mas wipe must not stack duplicate profile
    sections onto the operator's file."""
    from ai_venture_studio.upstream import init_workspace

    root = tmp_path / "twice"
    root.mkdir()
    (root / "CLAUDE.md").write_text("# mine\n\n- rule one\n", encoding="utf-8")
    init_workspace(root, "twice", "web")
    import shutil

    shutil.rmtree(root / ".mas")
    init_workspace(root, "twice", "web")
    assert (root / "CLAUDE.md").read_text().count("## avs profile: web") == 1


# --- the thin scope tier reaches the builder (gap 5) -------------------------


def test_scope_tier_is_recorded_in_the_workspace(tmp_path):
    """SCOPE_TIERS existed in the PRD and at the outer→inner handoff, and
    `scope_tier` appeared nowhere in the build path: a human could decide
    'thin' at Gate PL1 and the planner would still emit a dozen tasks."""
    import yaml

    from ai_venture_studio.upstream import init_workspace

    root = init_workspace(tmp_path / "thin", "thin", "web", scope_tier="thin")
    data = yaml.safe_load((root / ".mas" / "project.yaml").read_text())
    assert data["scope_tier"] == "thin"


def test_an_unknown_tier_is_refused_at_init(tmp_path):
    import pytest

    from ai_venture_studio.upstream import init_workspace

    with pytest.raises(ValueError, match="scope_tier"):
        init_workspace(tmp_path / "bad", "bad", "web", scope_tier="turbo")


def test_the_default_tier_is_standard_and_unchanged(tmp_path):
    import yaml

    from ai_venture_studio.upstream import init_workspace

    root = init_workspace(tmp_path / "std", "std", "web")
    data = yaml.safe_load((root / ".mas" / "project.yaml").read_text())
    assert data["scope_tier"] == "standard"


def test_thin_narrows_the_planner_and_standard_is_untouched():
    """The tier has to bite where scope is actually decided — the planner
    prompt — not merely be recorded."""
    from ai_venture_studio.upstream.plan import planner_system

    thin = planner_system("thin")
    standard = planner_system("standard")
    assert "EXACTLY 1-3 tasks" in thin
    assert "end to end" in thin
    assert "3-12 tasks" in standard
    assert "EXACTLY 1-3" not in standard
    # an unknown tier falls back to standard rather than inventing a policy
    assert planner_system("turbo") == standard
    # every tier keeps the rules that are not about scope size
    for text in (thin, standard, planner_system("deep")):
        assert "no cycles" in text
        assert "NO meta-tasks" in text


def test_thin_caps_the_planning_budget():
    """A thin slice that estimates like a full build is not thin, so the cap
    is enforced by budget_check rather than left to the prompt."""
    from ai_venture_studio.upstream.plan import _TIER_BUDGET_CAP, Task, budget_check

    assert _TIER_BUDGET_CAP["thin"] <= 10
    tasks = [Task(id=f"t{i}", title="x", estimate_hours=8) for i in range(3)]
    assert budget_check(tasks, _TIER_BUDGET_CAP["thin"]), "24h passed a thin cap"
    assert budget_check([Task(id="t1", title="x", estimate_hours=6)],
                        _TIER_BUDGET_CAP["thin"]) == []


def test_the_thin_tier_task_cap_bites_deterministically():
    """"EXACTLY 1-3 tasks" was planner-prompt text only, so the model could
    ignore it and nothing noticed."""
    from ai_venture_studio.upstream.plan import Task, tier_check

    four = [Task(id=f"t{i}", title="x", estimate_hours=1) for i in range(4)]
    assert tier_check(four, "thin"), "a 4-task thin plan passed"
    assert tier_check(four[:3], "thin") == []
    # wider tiers have no task cap
    assert tier_check(four, "standard") == []
    assert tier_check(four, "deep") == []
