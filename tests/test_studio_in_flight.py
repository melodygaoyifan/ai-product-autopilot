"""While a foreground step runs, every page must say so.

Reported from a live session: "正在处理界面会自动跳到前一个界面" — the working
page jumps back to the previous screen. The thinking page reloaded `/` on a
timer, `/` had no idea a step was in flight, so it rendered the page the
founder had just left. The step was still running; the UI said otherwise,
which reads as "my click did nothing".
"""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

import ai_venture_studio.upstream.autopilot as autopilot
from ai_venture_studio.studio import create_studio_app
from ai_venture_studio.upstream import init_workspace


@pytest.fixture
def in_flight(tmp_path):
    """A Studio with /fdr blocked mid-run, so `thinking` is populated."""
    root = init_workspace(tmp_path / "flight", "flight", "web")
    started, release = threading.Event(), threading.Event()

    def slow(*args, **kwargs):
        started.set()
        release.wait(timeout=10)

    original = autopilot.run_autopilot
    autopilot.run_autopilot = slow
    client = TestClient(
        create_studio_app(root, spawn=lambda r: 1, provider="mock"),
        raise_server_exceptions=False,
    )
    worker = threading.Thread(
        target=lambda: client.post("/fdr", data={"fdr": "# a\nb\n"})
    )
    worker.start()
    assert started.wait(timeout=10), "the blocked run never started"
    try:
        yield client, root
    finally:
        release.set()
        worker.join(timeout=10)
        autopilot.run_autopilot = original


def test_home_says_it_is_working_instead_of_the_previous_page(in_flight):
    client, _ = in_flight
    page = client.get("/").text
    assert "Working on it" in page
    # …and specifically NOT the describe state it would otherwise render
    assert "<textarea name=fdr" not in page


def test_the_working_page_reloads_itself_rather_than_bouncing_away(in_flight):
    """The reload has to come back to a page that still says 'working' —
    that is what makes it a poll instead of a bounce."""
    client, _ = in_flight
    assert "location.href='/'" in client.get("/").text
    assert "Working on it" in client.get("/").text  # the reload lands here


def test_the_form_door_also_reports_work_in_flight(in_flight):
    client, _ = in_flight
    assert "Working on it" in client.get("/?form=1").text


def test_the_conversation_reports_work_in_flight(in_flight):
    client, _ = in_flight
    assert "Working on it" in client.get("/chat").text


def test_the_page_returns_to_normal_once_the_step_lands(tmp_path):
    """The poll must terminate: with nothing in flight, / renders the real
    state again."""
    root = init_workspace(tmp_path / "done", "done", "web")
    client = TestClient(create_studio_app(root, spawn=lambda r: 1, provider="mock"))
    page = client.get("/").text
    assert "Working on it" not in page
    assert "One question at a time" in page


def test_a_failure_reaches_the_page_that_is_actually_watching(tmp_path):
    """The failure page is returned to the POST that raised — but the
    working page has navigated away from that request by then. Without a
    hand-off the founder sees a spinner, then an ordinary page, and never
    learns the step failed. Reported as 点了 check 以后一直在转.
    """
    root = init_workspace(tmp_path / "lost", "lost", "web")
    original = autopilot.run_autopilot

    def boom(*args, **kwargs):
        raise ValueError("brief failed schema after 4 attempts")

    autopilot.run_autopilot = boom
    try:
        client = TestClient(
            create_studio_app(root, spawn=lambda r: 1, provider="mock"),
            raise_server_exceptions=False,
        )
        # The POST that raises — its response is what the browser discards.
        client.post("/fdr", data={"fdr": "# a\nb\n"}, follow_redirects=True)
        # The reload the working page does is what the founder is looking at.
        landed = client.get("/").text
    finally:
        autopilot.run_autopilot = original

    assert "did not finish" in landed
    assert "brief failed schema" in landed


def test_the_failure_is_shown_once_and_then_cleared(tmp_path):
    """A sticky error would make the workspace look broken forever."""
    root = init_workspace(tmp_path / "once", "once", "web")
    original = autopilot.run_autopilot

    def boom(*args, **kwargs):
        raise ValueError("transient thing")

    autopilot.run_autopilot = boom
    try:
        client = TestClient(
            create_studio_app(root, spawn=lambda r: 1, provider="mock"),
            raise_server_exceptions=False,
        )
        client.post("/fdr", data={"fdr": "# a\nb\n"}, follow_redirects=True)
        assert "transient thing" in client.get("/").text
        assert "transient thing" not in client.get("/").text
    finally:
        autopilot.run_autopilot = original


def test_a_stale_failure_does_not_ambush_a_later_visitor(tmp_path, monkeypatch):
    """An hour-old error is not news, it is a scare. Observed: a failure
    nobody had loaded the page for was still queued, so the first visit
    after a SUCCESSFUL build showed "That step did not finish" ahead of the
    product."""
    import ai_venture_studio.studio as studio_mod

    root = init_workspace(tmp_path / "stale", "stale", "web")
    original = autopilot.run_autopilot

    def boom(*args, **kwargs):
        raise ValueError("an old failure")

    autopilot.run_autopilot = boom
    try:
        client = TestClient(
            create_studio_app(root, spawn=lambda r: 1, provider="mock"),
            raise_server_exceptions=False,
        )
        client.post("/fdr", data={"fdr": "# a\nb\n"}, follow_redirects=True)

        # Time passes — well past the window the working page reloads in.
        # `_take_fresh_failure` imports time inside the function, so the
        # module attribute is what has to move.
        import time as _time

        later = _time.monotonic() + studio_mod._FAILURE_TTL_S + 60
        monkeypatch.setattr(_time, "monotonic", lambda: later)

        landed = client.get("/").text
    finally:
        autopilot.run_autopilot = original

    assert "an old failure" not in landed
    assert "did not finish" not in landed


def test_a_fresh_failure_is_still_delivered(tmp_path):
    """The expiry must not undo the hand-off it was added to protect."""
    root = init_workspace(tmp_path / "fresh", "fresh", "web")
    original = autopilot.run_autopilot

    def boom(*args, **kwargs):
        raise ValueError("just happened")

    autopilot.run_autopilot = boom
    try:
        client = TestClient(
            create_studio_app(root, spawn=lambda r: 1, provider="mock"),
            raise_server_exceptions=False,
        )
        client.post("/fdr", data={"fdr": "# a\nb\n"}, follow_redirects=True)
        assert "just happened" in client.get("/").text
    finally:
        autopilot.run_autopilot = original
