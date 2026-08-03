"""A sequential build has one module in flight, so the page shows one NOW.

Seen in a real live run at 1:25 elapsed: two DONE, one BUILD_FAILED, and
three NOWs — because both renderers read "pending + a step" as in-flight,
and every task that had ever emitted a step still carried its last one. At
most one of those three could have been true.
"""
from __future__ import annotations

import os
import shutil

import pytest
import yaml
from fastapi.testclient import TestClient

from ai_venture_studio.studio import _task_states, create_studio_app
from ai_venture_studio.upstream import init_workspace, progress

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


@pytest.fixture
def three_started(tmp_path):
    """A plan whose first three tasks have all narrated something, the way a
    run with a review-fix pass and a retry leaves the journal."""
    root = init_workspace(tmp_path / "seq", "seq", "web")
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "plan.yaml").write_text(yaml.safe_dump({
        "status": "locked", "brief_title": "x", "tasks": [
            {"id": "t1", "title": "one", "estimate_hours": 1},
            {"id": "t2", "title": "two", "estimate_hours": 1},
            {"id": "t3", "title": "three", "estimate_hours": 1},
        ]}), encoding="utf-8")
    progress.step(root, "t1", "build", "writing the code")
    progress.step(root, "t2", "build", "fixing 1 serious issue(s) the review found")
    progress.step(root, "t3", "build", "working out how to build: three")
    (root / ".mas").mkdir(exist_ok=True)
    (root / ".mas" / "build.pid").write_text(str(os.getpid()), encoding="utf-8")
    return root


def test_only_the_task_the_run_is_on_carries_a_step(three_started):
    states = {t["id"]: t["step"] for t in _task_states(three_started)}
    assert states["t3"], "the live task lost its narration"
    assert states["t1"] == "" and states["t2"] == "", (
        "a task the run has moved past still claims to be working"
    )


def test_the_page_shows_exactly_one_now(three_started):
    client = TestClient(
        create_studio_app(three_started, spawn=lambda r: 1, provider="mock")
    )
    page = client.get("/").text
    assert "Building" in page
    assert page.count(">NOW<") == 1, "a sequential build showed several NOWs"
    assert page.count(">QUEUED<") == 2


def test_the_status_payload_agrees_with_the_page(three_started):
    """Server and poll JS share one mapping, so they cannot drift: the
    payload carries a step only for the task that has one."""
    client = TestClient(
        create_studio_app(three_started, spawn=lambda r: 1, provider="mock")
    )
    tasks = client.get("/status").json()["tasks"]
    with_steps = [t["id"] for t in tasks if t["step"]]
    assert with_steps == ["t3"]
