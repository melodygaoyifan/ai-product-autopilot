"""Repo comprehension (gap 3): read a codebase the system did not build.

Before this, "understanding an existing codebase" was `blast_radius` matching
FDR words against file *path strings* — it never read a byte of content — plus
a 200-path file list for the planner. `.mas/deps.yaml` had to be hand-written
and `arch_contract_check`, which compares imports against it, had no
production caller.
"""

from __future__ import annotations

import yaml

from ai_venture_studio.upstream.comprehend import (
    comprehend_repo,
    derive_deps,
    render_summary,
    write_map,
)


def _repo(tmp_path):
    """A small polyglot app with a real import edge and a route."""
    root = tmp_path / "legacy"
    (root / "app").mkdir(parents=True)
    (root / "core").mkdir()
    (root / "tests").mkdir()
    (root / "node_modules" / "junk").mkdir(parents=True)

    (root / "app" / "main.py").write_text(
        "from core import store\n"
        '@app.get("/tasks")\n'
        "def list_tasks(): return store.all()\n",
        encoding="utf-8",
    )
    (root / "app" / "ui.js").write_text("fetch('/tasks')\n", encoding="utf-8")
    (root / "core" / "store.py").write_text(
        "import sqlite3\ndef all(): ...\n", encoding="utf-8"
    )
    (root / "tests" / "test_store.py").write_text(
        "from core import store\ndef test_all(): ...\n", encoding="utf-8"
    )
    # vendored code must not shape the map
    (root / "node_modules" / "junk" / "index.js").write_text(
        "module.exports = 1\n", encoding="utf-8"
    )
    return root


def test_the_map_is_derived_from_the_code(tmp_path):
    result = comprehend_repo(_repo(tmp_path))

    assert result.languages["python"] == 3
    assert result.languages["javascript"] == 1
    modules = {m.name: m for m in result.modules}
    assert set(modules) >= {"app", "core", "tests"}
    assert modules["app"].files == 2
    assert modules["core"].lines > 0
    assert "app/main.py" in result.entry_points


def test_import_edges_come_from_real_imports(tmp_path):
    """The edge app→core exists because main.py imports it, not because
    somebody declared it."""
    result = comprehend_repo(_repo(tmp_path))
    modules = {m.name: m for m in result.modules}
    assert modules["app"].imports == ["core"]
    assert modules["core"].imports == []  # sqlite3 is not a repo module


def test_vendored_directories_are_excluded(tmp_path):
    result = comprehend_repo(_repo(tmp_path))
    assert all("node_modules" not in m.name for m in result.modules)
    assert result.languages["javascript"] == 1  # only app/ui.js


def test_the_http_surface_is_discovered(tmp_path):
    """Route drift between sibling specs is a real observed defect; the map
    exposes the surface that already exists so a planner can match it."""
    result = comprehend_repo(_repo(tmp_path))
    assert any(route.endswith("/tasks") for route in result.routes)


def test_tests_are_located_and_their_absence_is_a_stated_note(tmp_path):
    result = comprehend_repo(_repo(tmp_path))
    assert result.has_tests
    assert "tests/test_store.py" in result.test_files

    bare = tmp_path / "bare"
    (bare / "src").mkdir(parents=True)
    (bare / "src" / "thing.py").write_text("x = 1\n", encoding="utf-8")
    empty = comprehend_repo(bare)
    assert not empty.has_tests
    assert any("no test files" in note for note in empty.notes)


def test_derived_deps_are_a_closed_graph_that_load_deps_accepts(tmp_path):
    """The derived baseline has to satisfy the arch lane's own loader, or it
    is a file nothing can use."""
    from ai_venture_studio.lanes.arch import load_deps

    result = comprehend_repo(_repo(tmp_path))
    deps = derive_deps(result)
    assert "core" in deps["modules"] and "app" in deps["modules"]
    assert deps["modules"]["app"]["may_import"] == ["core"]
    assert "tests" not in deps["modules"]  # test code is not the design
    # honest about what it is
    assert "not a declared design" in deps["derived_from"]
    load_deps(yaml.safe_dump(deps))  # raises if the graph is not closed


def test_the_map_persists_and_round_trips(tmp_path):
    root = _repo(tmp_path)
    result = comprehend_repo(root)
    path = write_map(result, root)
    assert path.exists()
    reloaded = yaml.safe_load(path.read_text())
    assert reloaded["total_files"] == result.total_files
    assert {m["name"] for m in reloaded["modules"]} == {
        m.name for m in result.modules
    }


def test_the_summary_is_prompt_shaped_and_names_what_a_planner_needs(tmp_path):
    text = render_summary(comprehend_repo(_repo(tmp_path)))
    assert "languages:" in text and "modules:" in text
    assert "app" in text and "core" in text
    assert "→ core" in text          # the edge is visible
    assert "/tasks" in text          # the existing surface is visible
    assert "tests:" in text


def test_an_empty_repo_maps_to_nothing_without_crashing(tmp_path):
    bare = tmp_path / "empty"
    bare.mkdir()
    result = comprehend_repo(bare)
    assert result.total_files == 0
    assert result.modules == []
    assert render_summary(result)  # still renders something honest


def test_a_flat_repo_gets_no_invented_package_root(tmp_path):
    """Guessing a package root on a flat repo would make deps.yaml describe a
    fiction."""
    flat = tmp_path / "flat"
    flat.mkdir()
    (flat / "a.py").write_text("x = 1\n", encoding="utf-8")
    (flat / "b.py").write_text("y = 2\n", encoding="utf-8")
    assert comprehend_repo(flat).package_root == ""


# --- the CLI entry paths -----------------------------------------------------


def _cli_repo(tmp_path):
    root = tmp_path / "svc-repo"
    (root / "svc").mkdir(parents=True)
    (root / "lib").mkdir()
    (root / "svc" / "api.py").write_text(
        'from lib import db\n@app.get("/orders")\ndef orders(): ...\n',
        encoding="utf-8",
    )
    (root / "lib" / "db.py").write_text("def all(): ...\n", encoding="utf-8")
    return root


def test_avs_map_writes_the_map_and_prints_the_summary(tmp_path):
    import shutil

    import pytest

    if shutil.which("git") is None:
        pytest.skip("git not on PATH")
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app

    root = _cli_repo(tmp_path)
    result = CliRunner().invoke(app, ["map", str(root)])
    assert result.exit_code == 0, result.output
    assert "svc" in result.output and "lib" in result.output
    assert (root / ".mas" / "codebase-map.yaml").exists()


def test_avs_map_exits_3_on_a_repo_with_nothing_readable(tmp_path):
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app

    bare = tmp_path / "nothing"
    bare.mkdir()
    result = CliRunner().invoke(app, ["map", str(bare)])
    assert result.exit_code == 3, "an unreadable repo passed silently"


def test_init_adopt_reads_the_repo_and_keeps_the_operators_claude_md(tmp_path):
    """The brownfield entry path that did not exist: before this, `avs init`
    on an existing repo destroyed CLAUDE.md and read nothing."""
    import shutil

    import pytest

    if shutil.which("git") is None:
        pytest.skip("git not on PATH")
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app

    root = _cli_repo(tmp_path)
    (root / "CLAUDE.md").write_text(
        "# Orders\n\n- money is integer cents\n", encoding="utf-8"
    )
    result = CliRunner().invoke(
        app, ["init", str(root), "--profile", "web", "--adopt"]
    )
    assert result.exit_code == 0, result.output
    assert "/orders" in result.output          # the surface was read
    assert (root / ".mas" / "codebase-map.yaml").exists()
    deps = yaml.safe_load((root / ".mas" / "deps.yaml").read_text())
    assert deps["modules"]["svc"]["may_import"] == ["lib"]
    claude = (root / "CLAUDE.md").read_text()
    assert "money is integer cents" in claude
    assert "## avs profile: web" in claude


def test_init_adopt_does_not_overwrite_a_hand_tightened_deps_graph(tmp_path):
    import shutil

    import pytest

    if shutil.which("git") is None:
        pytest.skip("git not on PATH")
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app

    root = _cli_repo(tmp_path)
    (root / ".mas").mkdir(exist_ok=True)
    (root / ".mas" / "deps.yaml").write_text(
        yaml.safe_dump({"modules": {"svc": {"may_import": []},
                                    "lib": {"may_import": []}}}),
        encoding="utf-8",
    )
    CliRunner().invoke(app, ["init", str(root), "--profile", "web", "--adopt"])
    deps = yaml.safe_load((root / ".mas" / "deps.yaml").read_text())
    assert deps["modules"]["svc"]["may_import"] == [], "hand-tightened graph lost"
