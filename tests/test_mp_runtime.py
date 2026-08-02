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

The driver itself speaks the automation protocol raw (the automator's
launch() AND connect() hang without diagnosis against IDE 2.01.2510290),
and judges a page by three signals, because "reLaunch did not throw" alone
once reported three blank pages as rendered: the visit succeeded, no
`has not been registered` console line, and a screenshot on disk.
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


def test_a_port_that_never_opens_is_a_skip_naming_both_remedies(
    project, monkeypatch
):
    """cli auto spawned, automation port stayed closed. Almost always the
    service port; a cold CLI boot hanging is the other observed cause —
    the skip names both and points at the CLI's own log."""
    monkeypatch.setattr(mp, "devtools_cli", lambda explicit=None: "/fake/cli")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/node")
    (project / "node_modules" / "miniprogram-automator").mkdir(
        parents=True, exist_ok=True
    )
    monkeypatch.setattr(
        mp, "_start_automation",
        lambda *a, **k: (None, 9421, "DevTools never accepted the automation "
                                     "connection … 服务端口 (Settings → Security "
                                     "→ Service Port) … cli-auto.log"),
    )

    report = mp.mp_runtime_check(project)

    assert report.status == "skipped"
    assert "服务端口" in report.detail
    assert "cli-auto.log" in report.detail


def test_a_page_that_never_registered_is_a_finding_not_a_render(
    project, monkeypatch
):
    """The avs-studio-3 lesson: reLaunch succeeds on a page whose JS threw
    before Page() — it just renders pure white. The driver reads the
    runtime's own console line and reports it as a failure."""
    _pretend_ready(project, monkeypatch)
    _driver_says(monkeypatch, {"pages": [{
        "path": "pages/index/index", "ok": False,
        "error": "Page() never registered — the page JS threw before "
                 "registration (broken require chains are the known cause)",
    }]})

    report = mp.mp_runtime_check(project)

    assert report.status == "failed"
    assert report.findings[0].rule == "page_did_not_render"
    assert "never registered" in report.findings[0].message


def test_rendered_pages_point_at_the_screenshot_evidence(project, monkeypatch):
    """"Rendered" from the protocol alone is weak evidence; the report must
    say where the judgeable pixels are."""
    _pretend_ready(project, monkeypatch)
    _driver_says(monkeypatch, {"pages": [{"path": "pages/index/index", "ok": True}]})

    report = mp.mp_runtime_check(project)

    assert report.status == "ok"
    assert report.screenshot_dir.endswith("mp-runtime")
    assert "screenshots" in report.detail


def test_the_automation_session_is_cleaned_up_even_on_driver_error(
    project, monkeypatch
):
    """A spawned cli auto must not outlive the check — zombie sessions
    queue-block every later automation handshake (observed: a 90-minute-old
    one hung three consecutive runs)."""
    torn_down = []

    class _Proc:
        def terminate(self):
            torn_down.append(True)

    monkeypatch.setattr(mp, "devtools_cli", lambda explicit=None: "/fake/cli")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(mp, "_start_automation", lambda *a, **k: (_Proc(), 9420, None))
    (project / "node_modules" / "miniprogram-automator").mkdir(
        parents=True, exist_ok=True
    )

    def _boom(*a, **k):
        raise RuntimeError("driver exploded")

    import subprocess

    monkeypatch.setattr(subprocess, "run", _boom)
    with pytest.raises(RuntimeError):
        mp.mp_runtime_check(project)
    assert torn_down == [True]


def _write_png(path, pixels):
    """Minimal RGB PNG encoder (filter 0) for fixture screenshots."""
    import struct
    import zlib

    height, width = len(pixels), len(pixels[0])
    raw = b"".join(
        b"\x00" + b"".join(bytes(px) for px in row) for row in pixels
    )

    def chunk(kind, body):
        payload = kind + body
        return (struct.pack(">I", len(body)) + payload
                + struct.pack(">I", zlib.crc32(payload)))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def test_a_flat_screenshot_is_detected_and_a_real_one_is_not(tmp_path):
    """The blank-page judge is the pixels, not the protocol: a page whose
    JS threw before Page() still reLaunches fine and sits on the stack —
    it is just one flat color. (The runtime's console line about it does
    not reliably reach a fresh automation session; the screenshot always
    exists.)"""
    flat = tmp_path / "flat.png"
    _write_png(flat, [[(246, 247, 249)] * 4 for _ in range(3)])
    assert mp._is_flat_png(flat)

    real = tmp_path / "real.png"
    rows = [[(246, 247, 249)] * 4 for _ in range(3)]
    rows[1][2] = (7, 193, 96)
    _write_png(real, rows)
    assert not mp._is_flat_png(real)

    not_png = tmp_path / "junk.png"
    not_png.write_bytes(b"not a png at all")
    assert not mp._is_flat_png(not_png), "junk must never fail a healthy page"


def test_a_blank_page_fails_the_check_even_when_the_protocol_says_ok(
    project, monkeypatch
):
    """End to end through mp_runtime_check: driver reports ok, screenshot
    is one flat color -> finding `page_blank`, status failed."""
    _pretend_ready(project, monkeypatch)
    _driver_says(monkeypatch, {"pages": [{"path": "pages/index/index", "ok": True}]})
    shot_dir = project / ".mas" / "mp-runtime"
    shot_dir.mkdir(parents=True)
    _write_png(shot_dir / "pages_index_index.png",
               [[(255, 255, 255)] * 4 for _ in range(3)])

    report = mp.mp_runtime_check(project)

    assert report.status == "failed"
    assert report.findings[0].rule == "page_blank"
    assert "flat color" in report.findings[0].message


def test_the_cli_success_marker_is_a_whole_line_never_a_substring():
    """This workspace's own path contains "auto" — a substring test would
    read every failure as a success and print the wrong diagnosis."""
    assert mp._cli_reported_auto_ok("- preparing\n\x1b[32m✔\x1b[39m auto\n")
    assert not mp._cli_reported_auto_ok("opening /Users/x/autoproduct-work/p\n")
    assert not mp._cli_reported_auto_ok("[error] IDE service port disabled\n")
    assert not mp._cli_reported_auto_ok("")


def test_a_timeout_after_the_cli_succeeded_blames_first_open_not_the_port(
    project, monkeypatch, tmp_path
):
    """Measured on the reference machine: a project DevTools had never opened
    took >300s to compile while the CLI printed `✔ auto`, and the port came
    up after the wait; the second run took 27s. Blaming the service port
    there sends someone to re-check a toggle that is already on."""
    monkeypatch.setattr(mp, "_port_open", lambda port: False)
    monkeypatch.setattr(mp, "devtools_cli", lambda explicit=None: "/fake/cli")

    class _Proc:
        def poll(self): return None
        def terminate(self): pass

    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _Proc())
    shot_dir = tmp_path / "shots"
    shot_dir.mkdir()
    log = shot_dir / "cli-auto.log"
    log.write_text("- preparing\n", encoding="utf-8")

    # The success marker must be written DURING the run, after the size
    # snapshot — a marker already on disk belongs to an earlier run.
    real_popen_stub = _Proc

    class _WritesTheMarker(real_popen_stub):
        def __init__(self, *a, **k):
            with log.open("a", encoding="utf-8") as handle:
                handle.write("✔ auto\n")

    monkeypatch.setattr(subprocess, "Popen", _WritesTheMarker)

    _proc, _port, detail = mp._start_automation(
        "/fake/cli", project, shot_dir=shot_dir, wait_s=0
    )

    assert "first-open cost" in detail
    assert "Re-run and it will be fast" in detail
    assert "服务端口" not in detail, "do not blame a toggle that is already on"


def test_a_success_marker_from_an_earlier_run_is_not_read_as_this_one(
    project, monkeypatch, tmp_path
):
    """The log is append-only forensics across runs, so the diagnosis must
    read only what THIS run wrote. Reading the whole file made a `✔ auto`
    left by an earlier successful run look like this run's success — and
    reported "first-open cost" for a session that had exited in 4s."""
    monkeypatch.setattr(mp, "_port_open", lambda port: False)

    class _Proc:
        def poll(self): return None
        def terminate(self): pass

    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _Proc())
    shot_dir = tmp_path / "shots"
    shot_dir.mkdir()
    (shot_dir / "cli-auto.log").write_text(
        "- preparing\n✔ auto\n", encoding="utf-8"   # a PREVIOUS run's success
    )

    _proc, _port, detail = mp._start_automation(
        "/fake/cli", project, shot_dir=shot_dir, wait_s=0
    )

    assert "first-open cost" not in detail, "that marker was not ours"
    assert "服务端口" in detail


def test_a_timeout_with_no_cli_success_still_names_the_service_port(
    project, monkeypatch, tmp_path
):
    monkeypatch.setattr(mp, "_port_open", lambda port: False)

    class _Proc:
        def poll(self): return None
        def terminate(self): pass

    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _Proc())
    shot_dir = tmp_path / "shots"
    shot_dir.mkdir()
    (shot_dir / "cli-auto.log").write_text("- initialize\n", encoding="utf-8")

    _proc, _port, detail = mp._start_automation(
        "/fake/cli", project, shot_dir=shot_dir, wait_s=0
    )

    assert "服务端口" in detail and "Service Port" in detail
    assert "will not flip for you" in detail


def test_api_keys_never_reach_the_node_driver(project, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-travel")
    assert "ANTHROPIC_API_KEY" not in mp._clean_env()


def _pretend_ready(project, monkeypatch):
    """DevTools, node, the automator and a listening automation port."""
    monkeypatch.setattr(mp, "devtools_cli", lambda explicit=None: "/fake/cli")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(mp, "_start_automation", lambda *a, **k: (None, 9420, None))
    (project / "node_modules" / "miniprogram-automator").mkdir(parents=True, exist_ok=True)


def _driver_says(monkeypatch, payload):
    import subprocess

    def _run(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps(payload) + "\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _run)
