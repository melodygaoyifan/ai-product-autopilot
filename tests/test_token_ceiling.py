"""The per-run termination bound.

Two things are pinned here and they pull in opposite directions, which is the
point: a build that loops must stop (this file's first half), and ADR-032 must
still hold — nothing refuses work over money (this file's second half).
"""

import shutil

import pytest

from ai_venture_studio import spend, testing as testing_mod
from ai_venture_studio.upstream import init_workspace
from ai_venture_studio.upstream.autopilot import (
    DEFAULT_TOKEN_CEILING,
    run_autopilot,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)

GOOD_FDR = """# 产品需求
小区团长发起团购接龙，邻居在小程序里下单，团长看到按商品汇总的数量和应收金额。
必须有：发起接龙、下单、汇总。暂时不要：在线支付。
成功：第一周 10 个团长发起过接龙。
"""


@pytest.fixture(autouse=True)
def _no_docker(monkeypatch):
    monkeypatch.setattr(testing_mod, "docker_available", lambda: False)
    import ai_venture_studio.upstream.build as build_mod

    monkeypatch.setattr(build_mod, "docker_available", lambda: False)


def _workspace(tmp_path):
    root = init_workspace(tmp_path / "prod", "prod", "miniprogram")
    (root / "FDR.md").write_text(GOOD_FDR, encoding="utf-8")
    return root


# --- the primitive -------------------------------------------------------


def test_tokens_since_counts_the_unflushed_buffer(tmp_path):
    """The answer is wanted DURING a run, and the ledger only learns about a
    call at the next flush. A reader that saw the file alone would report a
    long run as having spent nothing."""
    spend.record("m", 100, 50, stage="build")
    assert spend.tokens_since(tmp_path, "2000-01-01T00:00:00+00:00") == 150

    spend.flush(tmp_path)
    # Same answer after the buffer became a file — counted once, not twice.
    assert spend.tokens_since(tmp_path, "2000-01-01T00:00:00+00:00") == 150


def test_tokens_since_excludes_earlier_runs(tmp_path):
    spend.record("m", 1_000, 0)
    spend.flush(tmp_path)
    mark = "2999-01-01T00:00:00+00:00"  # after everything recorded above
    assert spend.tokens_since(tmp_path, mark) == 0


# --- the bound -----------------------------------------------------------


def test_a_looping_build_halts_with_its_work_intact(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    # The bound is read through `tokens_since`; forcing it here tests the halt
    # itself rather than the mock provider's token accounting.
    monkeypatch.setattr(spend, "tokens_since", lambda *a, **k: 999_999_999)

    result = run_autopilot(
        root, root / "FDR.md", provider="mock", yes=True, token_ceiling=1_000
    )

    assert result.status == "halted"
    # Not a crash and not a silent stop: the run says what stopped it.
    halt = [line for line in result.auto_approvals if line.startswith("HALTED:")]
    assert len(halt) == 1
    assert "termination bound" in halt[0]
    assert "Nothing was refused over money" in halt[0]
    # Stopped BETWEEN tasks — the boundary where stopping is free, because a
    # task never started leaves no half-written workspace to rebuild.
    assert result.outcomes == []
    # A halted run is not a completed one, so it takes no undo checkpoint.
    from ai_venture_studio.upstream.autopilot import checkpoints

    assert checkpoints(root) == []


def test_halting_is_resumable_not_a_failure(tmp_path, monkeypatch):
    """A halted run must not poison the workspace: lifting the bound and
    re-running builds the plan."""
    root = _workspace(tmp_path)
    monkeypatch.setattr(spend, "tokens_since", lambda *a, **k: 999_999_999)
    halted = run_autopilot(
        root, root / "FDR.md", provider="mock", yes=True, token_ceiling=1_000
    )
    assert halted.status == "halted"

    monkeypatch.setattr(spend, "tokens_since", lambda *a, **k: 0)
    resumed = run_autopilot(root, root / "FDR.md", provider="mock", yes=True)
    assert resumed.status == "completed", [o.model_dump() for o in resumed.outcomes]
    assert len(resumed.outcomes) == 3


def test_zero_disables_the_bound(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    monkeypatch.setattr(spend, "tokens_since", lambda *a, **k: 999_999_999)
    result = run_autopilot(
        root, root / "FDR.md", provider="mock", yes=True, token_ceiling=0
    )
    assert result.status == "completed", [o.model_dump() for o in result.outcomes]


def test_the_default_never_stops_an_ordinary_build(tmp_path):
    """The bound is a runaway backstop, not a budget: a normal run must not
    come near it."""
    root = _workspace(tmp_path)
    result = run_autopilot(root, root / "FDR.md", provider="mock", yes=True)
    assert result.status == "completed", [o.model_dump() for o in result.outcomes]
    assert DEFAULT_TOKEN_CEILING >= 10_000_000


# --- ADR-032 still holds -------------------------------------------------


def test_a_build_still_never_refuses_over_money(tmp_path):
    """The bound counts tokens, never dollars, and no price table can make it
    fire. A month of heavy spend at any price must still build."""
    root = _workspace(tmp_path)
    (root / ".mas").mkdir(exist_ok=True)
    (root / ".mas" / "cost-model.yaml").write_text(
        "models:\n  mock:\n    input_per_mtok: 1000000.0\n"
        "    output_per_mtok: 1000000.0\n",
        encoding="utf-8",
    )
    for _ in range(50):
        spend.record("mock", 1_000_000, 1_000_000)
    spend.flush(root)

    result = run_autopilot(root, root / "FDR.md", provider="mock", yes=True)
    assert result.status == "completed", [o.model_dump() for o in result.outcomes]
