"""小程序 must LOAD, not just pass its own tests.

The web profile has had a boot gate since product-bench run 4, where every
built task passed and then failed every probe because the server never
listened. The mini-program profile never got the equivalent — and a real run
built nine modules and seven page directories, all green, with no app.json
and no app.js. WeChat DevTools could not open the project, and not one page
was reachable. 1431 hermetic tests were passing at the time.
"""
from __future__ import annotations

import json

import pytest

from ai_venture_studio.upstream.build import _miniprogram_gate, _miniprogram_root


def _page(root, name, *, wxml=True):
    d = root / "pages" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.js").write_text("Page({})", encoding="utf-8")
    if wxml:
        (d / f"{name}.wxml").write_text("<view/>", encoding="utf-8")


def _loadable(root, pages=("mall",)):
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.js").write_text("App({})", encoding="utf-8")
    (root / "app.json").write_text(
        json.dumps({"pages": [f"pages/{p}/{p}" for p in pages]}), encoding="utf-8"
    )
    for p in pages:
        _page(root, p)


def test_a_loadable_project_passes(tmp_path):
    _loadable(tmp_path / "miniprogram")
    assert _miniprogram_gate(tmp_path) is None


def test_the_exact_shape_the_real_run_produced_is_caught(tmp_path):
    """Seven pages, no app.json, no app.js — 9/9 'built'."""
    root = tmp_path / "miniprogram"
    for name in ("mall", "cart", "orders", "delivery", "share"):
        _page(root, name)

    failure = _miniprogram_gate(tmp_path)

    assert failure is not None
    assert "app.json is missing entirely" in failure
    assert "app.js is missing" in failure
    assert "pages/mall/mall" in failure


def test_a_page_nobody_registered_is_unreachable(tmp_path):
    root = tmp_path / "miniprogram"
    _loadable(root, pages=("mall",))
    _page(root, "orphan")

    failure = _miniprogram_gate(tmp_path)
    assert failure is not None
    assert "pages/orphan/orphan" in failure
    assert "not in app.json" in failure


def test_an_empty_pages_array_launches_nothing(tmp_path):
    root = tmp_path / "miniprogram"
    root.mkdir(parents=True)
    (root / "app.js").write_text("App({})", encoding="utf-8")
    (root / "app.json").write_text(json.dumps({"pages": []}), encoding="utf-8")
    assert "no `pages`" in _miniprogram_gate(tmp_path)


def test_a_registered_page_that_does_not_exist_is_caught(tmp_path):
    root = tmp_path / "miniprogram"
    root.mkdir(parents=True)
    (root / "app.js").write_text("App({})", encoding="utf-8")
    (root / "app.json").write_text(
        json.dumps({"pages": ["pages/ghost/ghost"]}), encoding="utf-8"
    )
    failure = _miniprogram_gate(tmp_path)
    assert "pages/ghost/ghost.js does not exist" in failure


def test_malformed_app_json_is_reported_as_such(tmp_path):
    root = tmp_path / "miniprogram"
    root.mkdir(parents=True)
    (root / "app.json").write_text("{ not json", encoding="utf-8")
    assert "not valid" in _miniprogram_gate(tmp_path)


def test_a_workspace_with_nothing_built_yet_is_not_this_gates_business(tmp_path):
    """Task 1 has not written a page yet; blocking here would be noise."""
    assert _miniprogram_gate(tmp_path) is None


@pytest.mark.parametrize("declared", [None, "src"])
def test_the_root_follows_project_config(tmp_path, declared):
    holder = tmp_path / "miniprogram"
    holder.mkdir(parents=True)
    config = {"compileType": "miniprogram"}
    if declared:
        config["miniprogramRoot"] = declared
    (holder / "project.config.json").write_text(json.dumps(config), encoding="utf-8")

    expected = (holder / declared).resolve() if declared else holder
    assert _miniprogram_root(tmp_path) == expected


def test_the_gate_only_runs_for_the_miniprogram_profile():
    """A web product has no app.json and must not be failed for it."""
    import inspect

    from ai_venture_studio.upstream import build

    source = inspect.getsource(build._run_build_inner)
    assert 'elif project.profile == "miniprogram"' in source
    assert "_miniprogram_gate(repo)" in source
