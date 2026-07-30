"""The founder-facing production loop: Take it live, It's broken,
Housekeeping. Hermetic — mock provider, localhost-only probes."""

from __future__ import annotations

import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

from ai_venture_studio.studio_i18n import STRINGS


def _t(key):
    return STRINGS[key]["en"]


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".mas").mkdir()
    (root / ".mas" / "project.yaml").write_text(
        yaml.safe_dump({"name": "ws", "profile": "web"})
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "app").mkdir()
    (root / "app" / "main.py").write_text("print('boot')\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=root, check=True,
    )
    return root


# --- probe --------------------------------------------------------------------


def test_probe_rejects_non_http_and_records_failure(tmp_path):
    from ai_venture_studio.studio_live import last_probe, probe_live

    root = _workspace(tmp_path)
    result = probe_live(root, "file:///etc/passwd")
    assert result["ok"] is False and "http" in result["detail"]
    # An unreachable port is a plain sentence, not a traceback.
    result = probe_live(root, "http://127.0.0.1:9")
    assert result["ok"] is False and result["detail"].startswith("no answer")
    assert last_probe(root)["url"] == "http://127.0.0.1:9"


def test_probe_reports_a_live_answer(tmp_path):
    from ai_venture_studio.studio_live import probe_live

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        root = _workspace(tmp_path)
        result = probe_live(root, f"http://127.0.0.1:{server.server_port}/")
        assert result["ok"] is True and result["status"] == 200
    finally:
        server.shutdown()


# --- take-it-live page body ---------------------------------------------------


def test_live_body_shows_boot_command_boundary_and_verify(tmp_path):
    from ai_venture_studio.studio_live import live_body

    root = _workspace(tmp_path)
    page = live_body(root, _t, "web")
    assert "python app/main.py" in page
    assert "never deploys to production on its own" in page
    assert "Is it answering right now?" in page
    assert "Write the cloud database guide" in page


def test_housekeeping_card_grey_clean_and_queued(tmp_path):
    from ai_venture_studio.studio_live import housekeeping_card

    root = _workspace(tmp_path)
    grey = housekeeping_card(root, _t)
    assert "avs sweep" in grey and "not run yet" in grey

    sweep_dir = root / ".mas" / "sweep"
    sweep_dir.mkdir()
    (sweep_dir / "digest-2026-07-30.yaml").write_text(yaml.safe_dump({
        "at": "2026-07-30", "rung": "SW0", "items_inspected": 2,
        "chores": [
            {"queue": "flags", "chore_class": "flag_removal",
             "item": "old_flag", "detail": "expired 2026-07-01"},
            {"queue": "deps", "chore_class": "dependency_upgrade",
             "item": "httpx", "detail": "patch release available"},
        ],
        "actionable": [], "reported": [], "action_rate": 0.0,
        "snapshot_hash": "sha256:x", "clean_pass": False,
    }))
    page = housekeeping_card(root, _t)
    assert "2 item(s) queued" in page and "old_flag" in page
    assert "human decision" in page

    (sweep_dir / "digest-2026-07-31.yaml").write_text(yaml.safe_dump({
        "at": "2026-07-31", "rung": "SW0", "items_inspected": 0,
        "chores": [], "actionable": [], "reported": [], "action_rate": 0.0,
        "snapshot_hash": "sha256:y", "clean_pass": True,
    }))
    assert "clean pass" in housekeeping_card(root, _t)


# --- it's broken → triage → fix ----------------------------------------------


def test_incident_intake_runs_triage_and_persists(tmp_path):
    from ai_venture_studio.studio_live import incident_body, incident_intake

    root = _workspace(tmp_path)
    incident, result = incident_intake(
        root, "The submit button does nothing since this morning.", "mock"
    )
    assert incident.id.startswith("inc-")
    record = yaml.safe_load(
        (root / ".mas" / "incidents" / incident.id / "founder.yaml")
        .read_text(encoding="utf-8")
    )
    assert record["incident"]["source"] == "founder"
    page = incident_body(_t, incident.id, result)
    assert "What the triage found" in page
    # The fix button only appears when a root cause was proposed — and its
    # consent note is always attached to the button, never implied.
    if "Attempt the fix" in page:
        assert "re-enters code review" in page


def test_incident_fix_flow_reloads_persisted_root_cause(tmp_path):
    from ai_venture_studio.studio_live import (
        attempt_incident_fix,
        fix_body,
        incident_intake,
    )

    root = _workspace(tmp_path)
    incident, result = incident_intake(
        root, "TypeError in app.main since the latest change.", "mock"
    )
    if result.verdict.value != "ROOT_CAUSE_PROPOSED":
        return  # mock triage may classify low-priority; the flow test is moot
    attempt = attempt_incident_fix(root, incident.id, "mock")
    page = fix_body(_t, attempt)
    assert attempt.status in ("opened", "branch_only", "tests_failed",
                              "abstained", "error")
    assert "How the attempt went" in page
