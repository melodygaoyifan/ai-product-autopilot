"""Resume must not skip work it cannot identify.

`avs create` re-runs discovery and planning on every invocation, and
planning is not deterministic — the same FDR produced these two plans:

    run 1   t4  结算页与下单记录界面
    run 2   t4  购物车与结算UI

Task ids are positional, so they always match. Matching on the id alone
therefore skipped a task that had never been built, and announced
"resumed: 1 task(s) already built" while doing it. Confirmed empirically
against a real workspace before this was fixed.
"""
from __future__ import annotations

from ai_venture_studio.upstream.autopilot import TaskOutcome, tasks_to_build
from ai_venture_studio.upstream.plan import Task


def _task(task_id, title):
    return Task(id=task_id, title=title, description="d", depends_on=[],
                lane="core", estimate_hours=1)


def test_the_same_id_naming_different_work_is_not_skipped():
    built = [TaskOutcome(task_id="t4", title="结算页与下单记录界面", status="built")]
    todo, skipped = tasks_to_build(built, [_task("t4", "购物车与结算UI")])
    assert [t.title for t in todo] == ["购物车与结算UI"]
    assert skipped == []


def test_genuinely_the_same_task_is_still_skipped():
    """The feature has to keep working — re-paying for a built module is
    the thing resume exists to prevent."""
    built = [TaskOutcome(task_id="t4", title="结算页", status="built")]
    todo, skipped = tasks_to_build(built, [_task("t4", "结算页")])
    assert todo == []
    assert skipped == ["t4"]


def test_a_failed_outcome_is_never_treated_as_done():
    for status in ("spec_blocked", "build_failed", "error"):
        outcomes = [TaskOutcome(task_id="t1", title="x", status=status)]
        todo, skipped = tasks_to_build(outcomes, [_task("t1", "x")])
        assert len(todo) == 1, status
        assert skipped == [], status


def test_a_mixed_plan_splits_correctly():
    outcomes = [
        TaskOutcome(task_id="t1", title="kept", status="built"),
        TaskOutcome(task_id="t2", title="old name", status="built"),
        TaskOutcome(task_id="t3", title="failed", status="build_failed"),
    ]
    tasks = [_task("t1", "kept"), _task("t2", "new name"), _task("t3", "failed")]
    todo, skipped = tasks_to_build(outcomes, tasks)
    assert [t.id for t in todo] == ["t2", "t3"]
    assert skipped == ["t1"]


def test_nothing_recorded_means_everything_is_todo():
    tasks = [_task("t1", "a"), _task("t2", "b")]
    todo, skipped = tasks_to_build([], tasks)
    assert len(todo) == 2 and skipped == []


def test_order_is_preserved():
    """The caller hands topological order in; it must come back out."""
    tasks = [_task(f"t{i}", f"task {i}") for i in range(1, 6)]
    todo, _ = tasks_to_build([], tasks)
    assert [t.id for t in todo] == ["t1", "t2", "t3", "t4", "t5"]
