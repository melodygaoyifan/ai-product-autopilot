"""What the system says about itself while it works, and after it fails.

Three defects these tests pin, all of the same shape — the system knew
something and threw it away:

1. A response truncated at the output cap was indistinguishable from a
   complete one, so a half-written source file reached disk.
2. A failed build reported "build gate still failing after max iterations"
   with the actual cause discarded one stack frame away.
3. A task in flight was `pending` for minutes with no observable step.
"""

from __future__ import annotations

import shutil

import pytest

from ai_venture_studio import testing as testing_mod
from ai_venture_studio.providers import (
    get_provider,
    last_response_truncated,
    last_stop_reason,
)
from ai_venture_studio.providers.mock import MockProvider
from ai_venture_studio.upstream import (
    approve_spec,
    init_workspace,
    run_build,
    run_spec_stage,
)
from ai_venture_studio.upstream import progress

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)


@pytest.fixture(autouse=True)
def _clear_truncation_flag():
    """A leaked `truncate_next` would truncate an unrelated test's first call."""
    MockProvider.truncate_next = False
    yield
    MockProvider.truncate_next = False


@pytest.fixture(autouse=True)
def _no_docker(monkeypatch):
    monkeypatch.setattr(testing_mod, "docker_available", lambda: False)
    import ai_venture_studio.upstream.build as build_mod

    monkeypatch.setattr(build_mod, "docker_available", lambda: False)


# --- the truncation signal ---------------------------------------------------

def test_stop_reason_is_recorded_on_every_response_not_only_empty_ones():
    get_provider("mock").complete(model="m", system="s", user="u")
    assert last_stop_reason() == "end_turn"
    assert last_response_truncated() is False


def test_a_cut_off_response_is_visible_to_its_caller():
    MockProvider.truncate_next = True
    get_provider("mock").complete(model="m", system="s", user="u")
    assert last_response_truncated() is True
    # And it does not stick: the next complete answer clears it, so one
    # truncated call cannot condemn every later call on the thread.
    get_provider("mock").complete(model="m", system="s", user="u")
    assert last_response_truncated() is False


def test_truncation_flag_does_not_leak_across_threads():
    """Voters and parallel lane builds run concurrently; one thread's cut-off
    response must not read as another thread's."""
    import threading

    get_provider("mock").complete(model="m", system="s", user="u")
    seen = []

    def worker():
        # This thread has made no call at all — it must see no stop reason,
        # not the main thread's.
        seen.append(last_stop_reason())

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert seen == [None]


# --- the build stage refuses a partial file set -------------------------------

def test_truncated_implementer_response_is_never_written_to_disk(tmp_path):
    root = init_workspace(tmp_path / "web", "web", "web")
    spec = run_spec_stage(root, "an item store API", provider="mock")
    approve_spec(root, spec.slug)

    # Truncate every attempt: the mock clears the flag after one reply, so
    # re-arm it from a patched hook that fires on each iteration.
    import ai_venture_studio.upstream.build as build_mod

    real_truncated = build_mod.last_response_truncated
    build_mod.last_response_truncated = lambda: True
    try:
        result = run_build(root, spec.slug, provider="mock")
    finally:
        build_mod.last_response_truncated = real_truncated

    assert result.status == "error"
    assert "truncated" in result.detail
    # The failure names the cap and the remedy rather than a symptom.
    assert "split it into smaller tasks" in result.detail
    # Nothing from the partial batch survived.
    assert not (root / "feature.py").exists()


def test_a_build_that_fails_its_tests_says_which_tests(tmp_path, monkeypatch):
    """The generic sentence stays; the cause now travels with it."""
    root = init_workspace(tmp_path / "web", "web", "web")
    spec = run_spec_stage(root, "an item store API", provider="mock")
    approve_spec(root, spec.slug)

    import ai_venture_studio.upstream.build as build_mod

    monkeypatch.setattr(
        build_mod,
        "combine_reports",
        None,
        raising=False,
    )
    # Force the suite to fail with a recognisable summary on every iteration.
    monkeypatch.setattr(
        build_mod,
        "_run_tests",
        lambda repo: testing_mod.TestReport(
            status="failed",
            summary="1 failed, 1 passed",
            detail="E   assert store.add('x') == 1",
        ),
    )
    result = run_build(root, spec.slug, provider="mock")

    assert result.status == "build_failed"
    assert "build gate still failing" in result.detail
    assert "last failure:" in result.detail
    assert "assert store.add" in result.detail
    # test_summary keeps the untrimmed version for anyone who wants it all.
    assert "assert store.add" in result.test_summary


def test_no_files_failure_records_what_the_model_actually_said(tmp_path):
    """"implementer returned no files" has three different causes; the record
    now distinguishes them."""
    from ai_venture_studio.upstream.build import _why_no_files

    narrated = _why_no_files("Sure! I'll implement that for you now.", [])
    assert "response began" in narrated
    assert "Sure!" in narrated

    discarded = _why_no_files("files: []", ["tests/test_x.py (skeleton kept — ...)"])
    assert "every file was discarded" in discarded
    assert "test_x.py" in discarded

    assert "response was empty" in _why_no_files("", [])


# --- the outcome record carries the diagnosis --------------------------------

def test_task_outcome_carries_the_build_diagnosis():
    """TaskOutcome used to keep only `detail`, which is how the bench
    scoreboard, outcomes.yaml and the founder's report all lost the cause."""
    from ai_venture_studio.upstream.autopilot import TaskOutcome

    outcome = TaskOutcome(
        task_id="t1", title="Item store", status="build_failed",
        detail="build gate still failing", iterations=3,
        files_written=["app/main.py"], test_summary="1 failed: assert x == 1",
    )
    assert outcome.iterations == 3
    assert outcome.test_summary == "1 failed: assert x == 1"
    # Older outcomes.yaml rows have none of these fields and must still load —
    # a resumed run must never crash on its own history.
    legacy = TaskOutcome.model_validate(
        {"task_id": "t0", "title": "old", "status": "built"}
    )
    assert legacy.iterations == 0
    assert legacy.files_written == []


# --- the step journal --------------------------------------------------------

def test_steps_are_appended_and_read_back_in_order(tmp_path):
    progress.step(tmp_path, "t1", "spec", "working out how to build it")
    progress.step(tmp_path, "t1", "build", "writing the code (attempt 1/3)")
    progress.step(tmp_path, "t2", "spec", "working out how to build it")

    assert [s["detail"] for s in progress.steps(tmp_path, "t1")] == [
        "working out how to build it",
        "writing the code (attempt 1/3)",
    ]
    assert progress.current(tmp_path)["task_id"] == "t2"
    latest = progress.latest_by_task(tmp_path)
    assert latest["t1"]["stage"] == "build"
    assert latest["t2"]["stage"] == "spec"


def test_a_half_written_last_line_does_not_destroy_the_history(tmp_path):
    """A build killed mid-write leaves a partial JSON line; the entries before
    it must still be readable."""
    progress.step(tmp_path, "t1", "build", "writing the code")
    journal = tmp_path / ".mas" / progress.JOURNAL_FILE
    with journal.open("a", encoding="utf-8") as handle:
        handle.write('{"at": "2026-07-28T00:00:00+00:00", "task_i')

    entries = progress.steps(tmp_path)
    assert len(entries) == 1
    assert entries[0]["detail"] == "writing the code"


def test_an_unwritable_journal_never_fails_the_build(tmp_path):
    """The journal is a record, never an input — a disk that cannot take a log
    line must not fail a build that is otherwise fine."""
    blocked = tmp_path / "ro"
    blocked.mkdir()
    (blocked / ".mas").write_text("not a directory", encoding="utf-8")
    progress.step(blocked, "t1", "build", "writing the code")  # must not raise
    assert progress.steps(blocked) == []


def test_the_sink_receives_steps_live_and_is_removable(tmp_path):
    """`avs create` narrates through this hook; a broken console must not take
    the build down with it."""
    lines: list[str] = []
    progress.set_sink(lines.append)
    try:
        progress.step(tmp_path, "t1", "build", "running your tests")
    finally:
        progress.set_sink(None)
    assert len(lines) == 1
    assert "t1" in lines[0] and "running your tests" in lines[0]

    def explode(_line: str) -> None:
        raise RuntimeError("terminal went away")

    progress.set_sink(explode)
    try:
        progress.step(tmp_path, "t1", "build", "still going")  # must not raise
    finally:
        progress.set_sink(None)
    assert progress.current(tmp_path)["detail"] == "still going"


def test_a_real_build_leaves_a_step_trail(tmp_path):
    """End to end: the steps a founder would have watched go by."""
    root = init_workspace(tmp_path / "web", "web", "web")
    spec = run_spec_stage(root, "an item store API", provider="mock")
    approve_spec(root, spec.slug)
    result = run_build(root, spec.slug, provider="mock")
    assert result.status == "built", result.detail

    details = [s["detail"] for s in progress.steps(root, spec.slug)]
    assert any("writing the code" in d for d in details)
    assert any("running your tests" in d for d in details)
    assert any("tests pass" in d for d in details)


def test_the_studio_renders_the_current_step_only_while_a_task_is_in_flight():
    from ai_venture_studio.studio import _task_list_html

    running = _task_list_html(
        [{"id": "t1", "title": "Item store", "state": "pending",
          "step": "running your tests"}]
    )
    assert "running your tests" in running

    # On a finished task the step is stale narration of something already done.
    finished = _task_list_html(
        [{"id": "t1", "title": "Item store", "state": "built",
          "step": "running your tests"}]
    )
    assert "running your tests" not in finished
