"""The wait before the first module must not be blank.

Reported live: "building ... 还是等待的时候光秃秃的啥也没有". The per-task
narration added in v0.60 only starts once tasks exist. Everything before that
— assess, brief, four charter voters with a verify pass each, leader,
planning — is the longest stretch of a run and rendered as a static
"planning…" the whole time.
"""
from __future__ import annotations

import os

import pytest
import yaml
from fastapi.testclient import TestClient

from ai_venture_studio.studio import create_studio_app
from ai_venture_studio.upstream import init_workspace, progress


@pytest.fixture
def building(tmp_path):
    """A workspace that looks like a build in flight, with no tasks yet."""
    root = init_workspace(tmp_path / "b", "b", "web")
    (root / ".mas" / "build.pid").write_text(str(os.getpid()), encoding="utf-8")
    client = TestClient(create_studio_app(root, spawn=lambda r: 1, provider="mock"))
    return client, root


def test_setup_is_a_real_task_id(tmp_path):
    """Steps before any task exists still need somewhere to live."""
    assert progress.SETUP
    progress.step(tmp_path, progress.SETUP, "plan", "reading your requirements")
    assert progress.current(tmp_path)["detail"] == "reading your requirements"


def test_the_building_page_shows_what_it_is_doing_before_any_task(building):
    client, root = building
    progress.step(root, progress.SETUP, "plan",
                  "four reviewers checking the brief")

    page = client.get("/").text

    assert "four reviewers checking the brief" in page
    assert "Building" in page


def test_status_carries_the_step_for_the_live_poll(building):
    client, root = building
    progress.step(root, progress.SETUP, "plan", "writing the brief")

    payload = client.get("/status").json()

    assert payload["running"] is True
    assert payload["tasks"] == []
    assert payload["step"] == "writing the brief"


def test_the_latest_step_wins(building):
    client, root = building
    progress.step(root, progress.SETUP, "plan", "reading your requirements")
    progress.step(root, progress.SETUP, "plan", "breaking it into modules")

    assert client.get("/status").json()["step"] == "breaking it into modules"


def test_no_step_yet_is_rendered_empty_not_broken(building):
    """A build that has not journalled anything must still render."""
    client, _ = building
    page = client.get("/").text
    assert "<p id=step></p>" in page
    assert client.get("/status").json()["step"] == ""


def test_per_task_steps_still_take_over_once_tasks_exist(building):
    """The setup line is for the gap BEFORE tasks; it must not replace the
    per-task checklist that follows."""
    client, root = building
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "plan.yaml").write_text(yaml.safe_dump({
        "status": "locked", "brief_title": "x",
        "tasks": [{"id": "t1", "title": "the first module", "estimate_hours": 1}],
    }), encoding="utf-8")
    progress.step(root, "t1", "build", "writing the code (attempt 1 of 3)")

    page = client.get("/").text

    assert "the first module" in page
    assert "writing the code (attempt 1 of 3)" in page


def test_the_interrupted_page_says_why_the_worker_died(tmp_path):
    """"The build was interrupted" was the entire story for a run that had
    died on a hard, repeatable provider error. The traceback was sitting in
    .mas/build.log, where no founder looks."""
    import subprocess
    import sys as _sys

    root = init_workspace(tmp_path / "why", "why", "web")
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "plan.yaml").write_text(yaml.safe_dump({
        "status": "locked", "brief_title": "x",
        "tasks": [{"id": "t1", "title": "a module", "estimate_hours": 1}],
    }), encoding="utf-8")
    dead = subprocess.Popen([_sys.executable, "-c", ""])
    dead.wait()
    (root / ".mas" / "build.pid").write_text(str(dead.pid), encoding="utf-8")
    (root / ".mas" / "build.log").write_text(
        "some rich traceback framing\n"
        "ValueError: Streaming is required for operations that may take "
        "longer than 10 minutes\n",
        encoding="utf-8",
    )

    page = TestClient(create_studio_app(root, provider="mock")).get("/").text

    assert "interrupted" in page.lower()
    assert "Streaming is required" in page
    assert "<details>" in page


def test_an_interrupted_build_with_no_log_still_renders(tmp_path):
    import subprocess
    import sys as _sys

    root = init_workspace(tmp_path / "nolog", "nolog", "web")
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "plan.yaml").write_text(yaml.safe_dump({
        "status": "locked", "brief_title": "x",
        "tasks": [{"id": "t1", "title": "a module", "estimate_hours": 1}],
    }), encoding="utf-8")
    dead = subprocess.Popen([_sys.executable, "-c", ""])
    dead.wait()
    (root / ".mas" / "build.pid").write_text(str(dead.pid), encoding="utf-8")

    page = TestClient(create_studio_app(root, provider="mock")).get("/").text
    assert "interrupted" in page.lower()
