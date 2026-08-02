"""Per-mode Studio UIs (v0.56): the mode is adaptable per request, and each
mode renders its persona's organizing surfaces from real workspace files.

The contracts under test:
- the mode switcher is on every page, current mode marked, others linked
  (a mode that isn't loudly visible invites mode errors);
- ?mode= beats cookie beats the startup default; an unknown ?mode= is a
  loud 400; the system never flips the mode on its own;
- engineer gets the review timeline and voter health read from `.mas/`;
- enterprise gets attestation *chain verification* (not a line count), the
  stage-activation grid, the dwell/rubber-stamp report, and automation
  arming state — with absence stated, never omitted.
"""

import datetime
import shutil

import pytest
import yaml
from fastapi.testclient import TestClient

from ai_venture_studio.adoption.attestation import append_attestation
from ai_venture_studio.editions import resolve_edition
from ai_venture_studio.studio import create_studio_app
from ai_venture_studio.upstream import init_workspace

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)


def _client(root, mode=None, lang="en"):
    return TestClient(
        create_studio_app(root, spawn=lambda r: 1, provider="mock",
                          lang=lang, mode=mode)
    )


def _workspace(tmp_path, name="prod", profile="web"):
    return init_workspace(tmp_path / name, name, profile)


def _fabricate_review(root, review_id="rev-abc123", verdict="APPROVE"):
    """A minimal mirror in the exact shape YamlMirror writes."""
    review_dir = root / ".mas" / "reviews" / review_id
    review_dir.mkdir(parents=True, exist_ok=True)
    t0 = datetime.datetime(2026, 7, 27, 10, 0, 0)
    (review_dir / "01-dor_gate.yaml").write_text(yaml.safe_dump({
        "step": 1, "node": "dor_gate", "written_at": t0.isoformat(),
        "dor_pass": True,
    }), encoding="utf-8")
    (review_dir / "02-final.yaml").write_text(yaml.safe_dump({
        "step": 2, "node": "final",
        "written_at": (t0 + datetime.timedelta(seconds=90)).isoformat(),
        "verdict": verdict,
    }), encoding="utf-8")
    return review_dir


# --- the switcher --------------------------------------------------------------


def test_mode_strip_is_on_every_page_in_every_mode(tmp_path):
    root = _workspace(tmp_path)
    for mode in (None, "engineer", "enterprise"):
        page = _client(root, mode=mode).get("/").text
        assert "class=modeswitch" in page  # the segmented switcher
        assert "/?mode=" in page  # the other modes stay one click away


def test_current_mode_is_marked_not_linked(tmp_path):
    root = _workspace(tmp_path)
    page = _client(root, mode="engineer").get("/").text
    # current: the active segment, styled and unlinked
    assert "<span class='seg on'>Engineer</span>" in page
    assert "href='/?mode=founder'" in page
    assert "href='/?mode=engineer'" not in page


def test_query_mode_overrides_the_default(tmp_path):
    root = _workspace(tmp_path)
    page = _client(root).get("/?mode=engineer").text
    assert "Build internals" in page


def test_query_mode_sets_a_cookie_that_persists(tmp_path):
    root = _workspace(tmp_path)
    client = _client(root)
    client.get("/?mode=enterprise")
    assert "Governance" in client.get("/").text  # cookie carried it


def test_unknown_query_mode_is_a_loud_400(tmp_path):
    root = _workspace(tmp_path)
    assert _client(root).get("/?mode=wizard").status_code == 400


def test_the_system_never_flips_the_mode_on_its_own(tmp_path):
    """Adaptable, not adaptive: resolving an edition after the user chose a
    mode must not override the user's cookie."""
    root = _workspace(tmp_path)
    client = _client(root)
    client.get("/?mode=founder")
    resolve_edition(root, "enterprise")
    assert "Governance" not in client.get("/").text


# --- engineer surfaces ----------------------------------------------------------


def test_engineer_lists_recent_reviews_with_verdicts(tmp_path):
    root = _workspace(tmp_path)
    _fabricate_review(root, "rev-abc123", verdict="REQUEST_CHANGES")
    page = _client(root, mode="engineer").get("/").text
    assert "Recent reviews" in page
    assert "rev-abc123" in page and "REQUEST_CHANGES" in page
    assert "href='/review/rev-abc123'" in page


def test_engineer_with_no_reviews_says_so(tmp_path):
    page = _client(_workspace(tmp_path), mode="engineer").get("/").text
    assert "Recent reviews" in page and "None yet." in page


def test_review_timeline_page_renders_the_mirror(tmp_path):
    root = _workspace(tmp_path)
    _fabricate_review(root, "rev-abc123")
    page = _client(root).get("/review/rev-abc123").text
    assert "Review timeline" in page
    assert "dor_gate" in page and "passed" in page
    assert "APPROVE" in page and "90.0s" in page


def test_review_page_guards_against_traversal_and_missing(tmp_path):
    root = _workspace(tmp_path)
    client = _client(root)
    assert client.get("/review/%2e%2e%2fsecrets").status_code == 404
    assert client.get("/review/no-such-review").status_code == 404


def test_engineer_voter_health_reads_the_logs(tmp_path):
    root = _workspace(tmp_path)
    log = root / ".mas" / "voters" / "security" / "log.yaml"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(yaml.safe_dump([
        {"review_id": "r1", "status": "OK", "findings": 2},
        {"review_id": "r2", "status": "BLOCKED_TOOL_FAILURE",
         "substituted_from": "gpt-5"},
    ]), encoding="utf-8")
    page = _client(root, mode="engineer").get("/").text
    assert "Voter health" in page
    assert "<code>security</code>" in page
    assert "<td>2</td><td>1</td><td>1</td>" in page  # runs · blocked · subst


# --- enterprise surfaces ---------------------------------------------------------


def test_enterprise_verifies_the_attestation_chain(tmp_path):
    root = _workspace(tmp_path)
    resolve_edition(root, "enterprise")
    append_attestation(root, {"gate": "review", "verdict": "APPROVE"})
    append_attestation(root, {"gate": "deploy", "decision": "ack"})
    page = _client(root).get("/").text
    assert "chain verified" in page and "<b>2</b>" in page


def test_enterprise_detects_a_tampered_ledger(tmp_path):
    root = _workspace(tmp_path)
    resolve_edition(root, "enterprise")
    append_attestation(root, {"gate": "review", "verdict": "APPROVE"})
    append_attestation(root, {"gate": "deploy", "decision": "ack"})
    ledger = root / ".mas" / "attestation" / "ledger.jsonl"
    lines = ledger.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("APPROVE", "REJECTED")  # rewrite history
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    page = _client(root).get("/").text
    assert "ATTESTATION CHAIN BROKEN at entry" in page


def test_enterprise_without_substrate_profile_states_the_absence(tmp_path):
    root = _workspace(tmp_path)
    page = _client(root, mode="enterprise").get("/").text
    assert "No substrate profile declared" in page


def test_enterprise_stage_grid_reads_the_substrate_ladder(tmp_path):
    root = _workspace(tmp_path)
    (root / ".mas" / "substrate-profile.yaml").write_text(yaml.safe_dump({
        "substrate": {"vcs": "git", "pr_flow": True, "ci": True,
                      "observability": ["none"], "languages": ["python"]},
    }), encoding="utf-8")
    page = _client(root, mode="enterprise").get("/").text
    assert "Stage activation" in page and "(S2)" in page
    assert "code_review" in page and "ACTIVE" in page
    assert "maintenance" in page and "STAGE_INACTIVE" in page
    assert "missing:" in page  # the exact gap, not just a red icon


def test_enterprise_dwell_report_states_when_nothing_is_measurable(tmp_path):
    page = _client(_workspace(tmp_path), mode="enterprise").get("/").text
    assert "Gate dwell" in page
    assert "nothing to measure" in page


def test_enterprise_automation_shows_disarmed_by_default(tmp_path):
    page = _client(_workspace(tmp_path), mode="enterprise").get("/").text
    assert "Automation policies" in page
    assert page.count("disarmed (the default)") == 2  # automerge + deploy-exec


def test_enterprise_automation_shows_who_armed_it_and_until_when(tmp_path):
    root = _workspace(tmp_path)
    (root / ".mas" / "automerge-policy.yaml").write_text(yaml.safe_dump({
        "enabled": True, "branches": ["main"], "armed_by": "melody",
        "expires_at": "2099-01-01",
    }), encoding="utf-8")
    page = _client(root, mode="enterprise").get("/").text
    assert "ARMED by" in page and "melody" in page and "2099-01-01" in page


# --- founder additions ------------------------------------------------------------


def test_founder_report_page_renders_the_correction_history(tmp_path):
    root = _workspace(tmp_path)
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "BUILD-REPORT.md").write_text("# done", encoding="utf-8")
    (root / "product" / "CORRECTION-LOG.md").write_text(
        "- fixed: button label\n", encoding="utf-8")
    page = _client(root).get("/").text
    assert "Correction history" in page and "button label" in page


def test_founder_without_corrections_has_no_empty_history_section(tmp_path):
    root = _workspace(tmp_path)
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "BUILD-REPORT.md").write_text("# done", encoding="utf-8")
    assert "Correction history" not in _client(root).get("/").text
