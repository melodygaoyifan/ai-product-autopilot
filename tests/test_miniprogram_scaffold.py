"""A 小程序 workspace must start loadable.

Two runs of the same FDR under the same profile produced two different
layouts — `miniprogram/pages/...` one time, `utils/` and `server/` at the
repo root the next — and neither produced an app.json. DevTools could open
neither. The loadability gate silently no-opped the second time because it
could not find a project to check: a gate can only check a layout somebody
guaranteed.
"""
from __future__ import annotations

import json

import pytest

from ai_venture_studio.upstream import init_workspace
from ai_venture_studio.upstream.build import _miniprogram_gate, _miniprogram_root


@pytest.fixture
def mp(tmp_path):
    return init_workspace(tmp_path / "mp", "假装消费", "miniprogram")


def test_a_fresh_workspace_already_passes_the_loadability_gate(mp):
    assert _miniprogram_gate(mp) is None


def test_devtools_has_something_to_open(mp):
    config = json.loads((mp / "project.config.json").read_text(encoding="utf-8"))
    assert config["miniprogramRoot"] == "miniprogram/"
    assert config["compileType"] == "miniprogram"
    assert _miniprogram_root(mp) == (mp / "miniprogram").resolve()


def test_the_entry_files_exist(mp):
    src = mp / "miniprogram"
    for f in ("app.js", "app.json", "app.wxss", "sitemap.json"):
        assert (src / f).exists(), f
    app = json.loads((src / "app.json").read_text(encoding="utf-8"))
    assert app["pages"] == ["pages/index/index"]


def test_the_launch_page_is_complete(mp):
    page = mp / "miniprogram" / "pages" / "index"
    for suffix in (".js", ".wxml", ".wxss", ".json"):
        assert (page / f"index{suffix}").exists(), suffix


def test_no_appid_is_invented(mp):
    """One run's implementer produced `wxb1e7d6736079f6c3` from nowhere —
    that is somebody's identifier or nobody's, and neither is ours to
    write."""
    config = json.loads((mp / "project.config.json").read_text(encoding="utf-8"))
    assert config["appid"] == "touristappid"


def test_the_project_name_reaches_the_title_bar(mp):
    app = json.loads((mp / "miniprogram" / "app.json").read_text(encoding="utf-8"))
    assert app["window"]["navigationBarTitleText"] == "假装消费"


def test_other_profiles_get_no_miniprogram_tree(tmp_path):
    web = init_workspace(tmp_path / "web", "w", "web")
    assert not (web / "miniprogram").exists()
    assert not (web / "project.config.json").exists()


def test_the_implementer_is_told_the_layout_is_not_its_choice():
    """The scaffold only helps if the writer knows to build into it."""
    from ai_venture_studio.upstream.workspace import load_profile

    hint = load_profile("miniprogram")["stack_hint"]
    assert "LAYOUT IS FIXED" in hint
    assert "miniprogram/app.json" in hint
    assert "`pages` array" in hint
    assert ".py test file" in hint


def test_the_scaffold_is_committed_so_tasks_extend_it(mp):
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=mp, capture_output=True, text=True, timeout=60
    ).stdout
    assert "miniprogram/app.json" in tracked
    assert "project.config.json" in tracked


def test_a_stray_miniprogram_directory_does_not_disable_the_gate(tmp_path):
    """Evidence beats directory names.

    A real workspace kept its mini-program at the repo root (app.json and
    pages/ there) beside a stray `miniprogram/` holding nothing but a
    .DS_Store and an api/ folder. The name heuristic picked the stray, found
    no app.json, and the gate answered "not my business" — a vacuous pass
    over a product with three registered pages, which is exactly the silent
    no-op this gate exists to prevent.
    """
    import json

    repo = tmp_path / "rootlayout"
    (repo / "pages" / "home").mkdir(parents=True)
    (repo / "miniprogram" / "api").mkdir(parents=True)      # the stray
    (repo / "miniprogram" / ".DS_Store").write_text("", encoding="utf-8")
    (repo / "app.json").write_text(
        json.dumps({"pages": ["pages/home/home"]}), encoding="utf-8"
    )
    (repo / "app.js").write_text("App({})\n", encoding="utf-8")
    (repo / "pages" / "home" / "home.js").write_text("Page({})\n", encoding="utf-8")
    (repo / "pages" / "home" / "home.wxml").write_text("<view/>\n", encoding="utf-8")

    assert _miniprogram_root(repo) == repo, "the app.json decides, not the name"
    assert _miniprogram_gate(repo) is None, "a complete root-layout project loads"

    # ...and the gate now actually judges it: break the page it registered.
    (repo / "pages" / "home" / "home.wxml").unlink()
    problems = _miniprogram_gate(repo)
    assert problems and "pages/home/home.wxml" in problems, (
        "a stray miniprogram/ must not buy silence about a missing page file"
    )
