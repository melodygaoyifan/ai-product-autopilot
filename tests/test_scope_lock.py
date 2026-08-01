"""Gate U2 means something now (item P1.2).

`approve_plan` has always written `status: locked`, and every later
`avs create` re-decomposed the brief anyway — so the lock was decoration,
the expensive upstream was re-paid on every invocation, and because
planning is not deterministic the second run produced a DIFFERENT plan
under the same positional ids. These tests pin the three behaviours that
fix costs nothing to get wrong: reuse, refusal, and the deliberate way out.
"""

import shutil

import pytest

from ai_venture_studio import testing as testing_mod
from ai_venture_studio.upstream import init_workspace
from ai_venture_studio.upstream.autopilot import run_autopilot
from ai_venture_studio.upstream.plan import (
    ScopeLocked,
    approve_plan,
    fdr_fingerprint,
    load_plan,
    reusable_plan,
    run_planning,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)

FDR = """# 产品需求
小区团长发起团购接龙，邻居在小程序里下单，团长看到按商品汇总的数量和应收金额。
必须有：发起接龙、下单、汇总。暂时不要：在线支付。
成功：第一周 10 个团长发起过接龙。
"""


@pytest.fixture(autouse=True)
def _no_docker(monkeypatch):
    monkeypatch.setattr(testing_mod, "docker_available", lambda: False)
    import ai_venture_studio.upstream.build as build_mod

    monkeypatch.setattr(build_mod, "docker_available", lambda: False)


def _locked_workspace(tmp_path):
    """A workspace whose plan is locked, the way `avs create --yes` leaves it."""
    root = init_workspace(tmp_path / "prod", "prod", "miniprogram")
    (root / "FDR.md").write_text(FDR, encoding="utf-8")
    run_autopilot(root, root / "FDR.md", provider="mock", yes=True)
    plan = load_plan(root)
    assert plan.status == "locked"
    assert plan.fdr_fingerprint == fdr_fingerprint(FDR)
    return root, plan


def test_locked_plan_is_reused_without_a_model_call(tmp_path):
    root, first = _locked_workspace(tmp_path)

    # A provider that would raise if planning ran at all: reuse has to be
    # free, not merely fast.
    again = run_planning(root, provider="no-such-provider")

    assert again.status == "locked"
    assert [t.id for t in again.tasks] == [t.id for t in first.tasks]
    assert [t.title for t in again.tasks] == [t.title for t in first.tasks]


def test_second_create_skips_discovery_and_planning(tmp_path, monkeypatch):
    """The whole point: re-running `avs create` on an unchanged FDR must
    not re-pay assess + discovery + four charter voters + planning."""
    root, first = _locked_workspace(tmp_path)

    import ai_venture_studio.upstream.autopilot as autopilot_mod

    def _never(*args, **kwargs):
        raise AssertionError("upstream re-ran on an unchanged, locked plan")

    monkeypatch.setattr(autopilot_mod, "run_discovery", _never)
    monkeypatch.setattr(autopilot_mod, "assess_fdr", _never)
    result = run_autopilot(root, root / "FDR.md", provider="mock", yes=True)

    assert result.status == "completed", [o.model_dump() for o in result.outcomes]
    assert any("reused the locked plan" in a for a in result.auto_approvals)
    # Same plan, same ids, same titles — which is what makes resume able to
    # recognize its own work.
    assert [t.title for t in load_plan(root).tasks] == [t.title for t in first.tasks]


def test_awaiting_confirmation_reuses_the_stored_text(tmp_path):
    root, _ = _locked_workspace(tmp_path)
    stored = (root / "product" / "CONFIRMATION.md").read_text(encoding="utf-8")

    result = run_autopilot(root, root / "FDR.md", provider="mock", yes=False)

    assert result.status == "awaiting_confirmation"
    assert stored.strip()[:40] in result.confirmation
    assert "已确认" in result.confirmation or "already approved" in result.confirmation


def test_changed_fdr_after_the_lock_is_refused_not_replanned(tmp_path):
    root, _ = _locked_workspace(tmp_path)
    (root / "FDR.md").write_text(FDR + "\n还要有：在线支付、退款。\n", encoding="utf-8")

    with pytest.raises(ScopeLocked) as exc:
        reusable_plan(root)
    assert "scope change after the lock" in str(exc.value)
    assert "--replan" in str(exc.value)

    # Through the autopilot it is a failed run carrying the explanation,
    # never a silent re-decomposition.
    result = run_autopilot(root, root / "FDR.md", provider="mock", yes=True)
    assert result.status == "failed"
    assert "locked" in result.confirmation


def test_reflowing_the_fdr_is_not_a_scope_change(tmp_path):
    root, first = _locked_workspace(tmp_path)
    (root / "FDR.md").write_text(FDR.replace("\n", "\n\n"), encoding="utf-8")

    reused = reusable_plan(root)

    assert reused is not None
    assert [t.title for t in reused.tasks] == [t.title for t in first.tasks]


def test_replan_discards_the_lock_deliberately(tmp_path):
    root, _ = _locked_workspace(tmp_path)
    (root / "FDR.md").write_text(FDR + "\n还要有：在线支付。\n", encoding="utf-8")

    replanned = run_planning(root, provider="mock", replan=True)

    assert replanned.status == "proposed"  # a fresh plan awaiting Gate U2
    assert replanned.fdr_fingerprint == fdr_fingerprint(
        (root / "FDR.md").read_text(encoding="utf-8")
    )


def test_a_plan_locked_before_fingerprints_is_still_honored(tmp_path):
    """Older workspaces have no fingerprint. Re-planning is the behaviour
    that loses work, so an unverifiable lock is honored, not discarded."""
    root, _ = _locked_workspace(tmp_path)
    plan = load_plan(root)
    plan.fdr_fingerprint = ""
    from ai_venture_studio.upstream.plan import _save

    _save(root, plan)
    (root / "FDR.md").write_text(FDR + "\n(edited)\n", encoding="utf-8")

    assert reusable_plan(root) is not None


def test_an_unapproved_plan_is_not_reused(tmp_path):
    """Only Gate U2 confers reuse: a proposed plan nobody locked is still
    just a proposal."""
    root = init_workspace(tmp_path / "p2", "p2", "miniprogram")
    (root / "FDR.md").write_text(FDR, encoding="utf-8")
    run_autopilot(root, root / "FDR.md", provider="mock", yes=False)  # pauses
    from ai_venture_studio.upstream.discover import approve_brief

    approve_brief(root)
    run_planning(root, provider="mock")
    assert load_plan(root).status == "proposed"

    assert reusable_plan(root) is None

    approve_plan(root)
    assert reusable_plan(root) is not None


def test_create_no_longer_demands_profile_for_an_existing_workspace(tmp_path):
    """Item 14: --profile answers a question only a NEW workspace has.

    Demanding it on every re-run made resume, `--yes` after a confirmation
    and every later feature an error — and a mistyped value would have read
    as a request to change what the product is.
    """
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app

    root = init_workspace(tmp_path / "mp", "mp", "miniprogram")
    (root / "FDR.md").write_text(FDR, encoding="utf-8")
    runner = CliRunner()

    ok = runner.invoke(app, ["create", str(root), "--provider", "mock", "--yes"])
    assert ok.exit_code == 0, ok.output

    # A profile that contradicts the workspace is refused, not applied:
    # that is a different product, and it belongs in its own directory.
    wrong = runner.invoke(
        app, ["create", str(root), "--profile", "web", "--provider", "mock"]
    )
    assert wrong.exit_code == 2
    assert "miniprogram" in wrong.output

    # A new workspace still has to say what it is.
    fresh = runner.invoke(
        app, ["create", str(tmp_path / "new"), "--provider", "mock"]
    )
    assert fresh.exit_code == 2
    assert "--profile is required" in fresh.output


def test_the_studio_form_releases_the_lock_it_would_otherwise_hit(tmp_path):
    """A founder rewriting the requirements in the Studio has asked for the
    scope to change — the refusal is for accidental CLI re-runs, not for
    the one form the product offers for asking."""
    from ai_venture_studio.upstream.plan import release_lock_if_fdr_changed

    root, _ = _locked_workspace(tmp_path)

    # Same words: the lock stands and the next run is free.
    assert release_lock_if_fdr_changed(root, FDR) is False
    assert load_plan(root).status == "locked"

    # Different words: the lock is released here, not surfaced as an error
    # two screens later.
    assert release_lock_if_fdr_changed(root, FDR + "\n还要有：在线支付。\n") is True
    assert load_plan(root).status == "proposed"
    assert reusable_plan(root) is None
