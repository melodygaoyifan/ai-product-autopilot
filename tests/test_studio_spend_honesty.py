"""A dollar figure is a claim. The building page must not make one it
cannot support.

Found by watching a real live build: 24 minutes in, with every model call
unpriced in that workspace, the page read "$0.00 so far". A founder reads
that as "this one is free"; it meant "this workspace has no price list".
"""
from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from ai_venture_studio import spend
from ai_venture_studio.studio import create_studio_app
from ai_venture_studio.upstream import init_workspace

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _studio(tmp_path):
    root = init_workspace(tmp_path / "money", "money", "web")
    return TestClient(create_studio_app(root, spawn=lambda r: 1, provider="mock")), root


def test_unpriced_calls_produce_no_figure_at_all(tmp_path):
    _client, root = _studio(tmp_path)
    spend.record("some-unpriced-model", 1000, 500)
    spend.flush(root)
    report = spend.month_report(root)
    assert report.calls == 1
    assert report.is_floor and report.spent_usd == 0, "fixture is not unpriced"

    page = _client_building_page(tmp_path, root)
    assert "$0.00" not in page, "an unpriced build reported a zero total"
    assert "0.00 so far" not in page


def test_a_priced_figure_keeps_its_floor_marker(tmp_path):
    """A lower bound reprinted as a total is the same lie, smaller."""
    _client, root = _studio(tmp_path)
    (root / ".mas").mkdir(exist_ok=True)
    (root / ".mas" / "cost-model.yaml").write_text(
        "prices:\n  priced-model:\n    input: 3.0\n    output: 15.0\n",
        encoding="utf-8"
    )
    spend.record("priced-model", 1_000_000, 0)
    spend.record("unpriced-model", 1000, 10)
    spend.flush(root)
    report = spend.month_report(root)
    assert report.is_floor and report.spent_usd > 0, "fixture is not a floor"

    page = _client_building_page(tmp_path, root)
    assert "≥$3.00" in page, "the floor marker was stripped off the figure"


def _client_building_page(tmp_path, root) -> str:
    """The building state: a live worker and a plan, so the meta line renders."""
    import os

    import yaml

    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "plan.yaml").write_text(yaml.safe_dump({
        "status": "locked", "brief_title": "x",
        "tasks": [{"id": "t1", "title": "one", "estimate_hours": 1}],
    }), encoding="utf-8")
    (root / ".mas").mkdir(exist_ok=True)
    (root / ".mas" / "build.pid").write_text(str(os.getpid()), encoding="utf-8")
    client = TestClient(create_studio_app(root, spawn=lambda r: 1, provider="mock"))
    page = client.get("/").text
    assert "Building" in page, "not the building state"
    return page
