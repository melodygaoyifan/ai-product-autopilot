"""The runtime half of the 小程序 loadability question (item 13).

The build-loop gate is static: it reads app.json and asks whether DevTools
*would* open the project. Whether the pages then render was, until now,
answerable only by a human opening the desktop app — which is why every
"it works" claim about a 小程序 ended in an unverified promise.

It is answerable, and these tests pin the honest part: every missing
precondition is a VISIBLE skip naming the remedy. A machine with no
DevTools, no node, no automator, or an un-toggled service port must never
produce something that reads like "the pages render".

Verified by hand on a machine that has DevTools installed: with the service
port off, the CLI prints "IDE service port disabled ... set Service Port
On" while miniprogram-automator, which spawns that same CLI and swallows
its stderr, just times out. That is why a timeout is classified as a skip.
"""

import json

import pytest

from ai_venture_studio.lanes import miniprogram as mp


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "p"
    (root / "miniprogram" / "pages" / "index").mkdir(parents=True)
    (root / "project.config.json").write_text(
        json.dumps({"miniprogramRoot": "miniprogram/"}), encoding="utf-8"
    )
    (root / "miniprogram" / "app.json").write_text(
        json.dumps({"pages": ["pages/index/index"]}), encoding="utf-8"
    )
    return root


def test_no_devtools_is_a_skip_that_says_why(project, monkeypatch):
    monkeypatch.setattr(mp, "devtools_cli", lambda explicit=None: None)

    report = mp.mp_runtime_check(project)

    assert report.status == "skipped"
    assert "not installed" in report.detail
    assert "CI" in report.detail, "it can never run in CI — say so"
    assert report.findings == []


def test_no_node_is_a_skip(project, monkeypatch):
    monkeypatch.setattr(mp, "devtools_cli", lambda explicit=None: "/fake/cli")
    monkeypatch.setattr("shutil.which", lambda name: None)

    report = mp.mp_runtime_check(project)

    assert report.status == "skipped"
    assert "node" in report.detail


def test_missing_automator_names_the_install_command(project, monkeypatch):
    monkeypatch.setattr(mp, "devtools_cli", lambda explicit=None: "/fake/cli")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/node")

    report = mp.mp_runtime_check(project)

    assert report.status == "skipped"
    assert "npm i -D miniprogram-automator" in report.detail


def test_a_disabled_service_port_is_a_skip_not_a_failure(project, monkeypatch):
    """The distinction that matters: nothing was checked. Reporting red here
    would read as "your pages are broken"."""
    _pretend_ready(project, monkeypatch)
    _driver_says(monkeypatch, {"error": "Error: Wait timed out after 30000 ms"})

    report = mp.mp_runtime_check(project)

    assert report.status == "skipped"
    assert "服务端口" in report.detail and "Service Port" in report.detail
    assert "will not flip for you" in report.detail


def test_pages_that_render_are_an_ok(project, monkeypatch):
    _pretend_ready(project, monkeypatch)
    _driver_says(monkeypatch, {"pages": [{"path": "pages/index/index", "ok": True}]})

    report = mp.mp_runtime_check(project)

    assert report.status == "ok"
    assert report.pages_checked == ["pages/index/index"]
    assert "1 registered page(s) rendered" in report.detail


def test_a_page_that_throws_on_load_is_a_finding(project, monkeypatch):
    _pretend_ready(project, monkeypatch)
    _driver_says(monkeypatch, {"pages": [
        {"path": "pages/index/index", "ok": False, "error": "TypeError: x is not a function"},
    ]})

    report = mp.mp_runtime_check(project)

    assert report.status == "failed"
    assert report.findings[0].rule == "page_did_not_render"
    assert "TypeError" in report.findings[0].message


def test_no_registered_pages_defers_to_the_static_gate(project, monkeypatch):
    _pretend_ready(project, monkeypatch)
    (project / "miniprogram" / "app.json").write_text(
        json.dumps({"pages": []}), encoding="utf-8"
    )

    report = mp.mp_runtime_check(project)

    assert report.status == "skipped"
    assert "registers no pages" in report.detail


def test_api_keys_never_reach_the_node_driver(project, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-travel")
    assert "ANTHROPIC_API_KEY" not in mp._clean_env()


def _pretend_ready(project, monkeypatch):
    """DevTools, node and the automator all present."""
    monkeypatch.setattr(mp, "devtools_cli", lambda explicit=None: "/fake/cli")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/node")
    (project / "node_modules" / "miniprogram-automator").mkdir(parents=True, exist_ok=True)


def _driver_says(monkeypatch, payload):
    import subprocess

    def _run(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps(payload) + "\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _run)
