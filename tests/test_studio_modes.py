"""Studio modes (v0.55): different users get different depths of the same UI.

The contract under test mirrors the editions' own (invariant 14.21, read
UI-side): a mode may only ADD visibility. Founder mode is the pre-mode UI
byte for byte; engineer and enterprise append read-only cards built from
the same workspace files the CLI writes.
"""

import re
import shutil

import pytest
import yaml
from fastapi.testclient import TestClient

from ai_venture_studio.editions import resolve_edition
from ai_venture_studio.studio import create_studio_app
from ai_venture_studio.studio_modes import StudioModeError, resolve_mode
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


def _fabricate_plan(root):
    """A locked plan with one built and one failed task, exactly as the CLI
    leaves them on disk."""
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "plan.yaml").write_text(yaml.safe_dump({
        "status": "locked", "brief_title": "x", "tasks": [
            {"id": "t1", "title": "URL store", "estimate_hours": 1},
            {"id": "t2", "title": "Shorten endpoint", "estimate_hours": 1},
        ]}), encoding="utf-8")
    spec_dir = root / "specs" / "url-store"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.yaml").write_text(yaml.safe_dump(
        {"request": "an item store (task:t1)", "built": True}), encoding="utf-8")
    (root / "product" / "outcomes.yaml").write_text(yaml.safe_dump(
        [{"task_id": "t2", "status": "spec_blocked"}]), encoding="utf-8")


# --- resolution ---------------------------------------------------------------


def test_no_edition_resolves_to_founder(tmp_path):
    root = _workspace(tmp_path)
    assert resolve_mode(root) == "founder"


@pytest.mark.parametrize("edition,expected", [
    ("solo", "founder"), ("engineer", "engineer"), ("enterprise", "enterprise"),
])
def test_edition_maps_to_mode(tmp_path, edition, expected):
    root = _workspace(tmp_path, name=edition)
    resolve_edition(root, edition)
    assert resolve_mode(root) == expected


def test_explicit_mode_wins_over_edition(tmp_path):
    root = _workspace(tmp_path)
    resolve_edition(root, "enterprise")
    assert resolve_mode(root, "founder") == "founder"


def test_explicit_mode_is_normalized(tmp_path):
    root = _workspace(tmp_path)
    assert resolve_mode(root, " Engineer ") == "engineer"


def test_unknown_explicit_mode_is_a_loud_startup_error(tmp_path):
    """Same policy as a missing i18n key: refuse at startup, don't serve the
    wrong audience quietly."""
    root = _workspace(tmp_path)
    with pytest.raises(StudioModeError):
        create_studio_app(root, spawn=lambda r: 1, provider="mock",
                          mode="wizard")


def test_a_corrupted_edition_file_does_not_take_the_studio_down(tmp_path):
    root = _workspace(tmp_path)
    (root / ".mas" / "edition.yaml").write_text("{unclosed", encoding="utf-8")
    assert resolve_mode(root) == "founder"
    assert "<title>" in _client(root).get("/").text


# --- founder: the default is unchanged -----------------------------------------


def test_founder_page_has_no_mode_cards(tmp_path):
    root = _workspace(tmp_path)
    page = _client(root).get("/").text
    assert "Build internals" not in page
    assert "Governance" not in page


def test_solo_edition_keeps_the_plain_founder_page(tmp_path):
    """The solo edition narrows the pipeline (WIP 1, weekly review); the UI
    reading of it is the plain founder flow, not a busier page."""
    root = _workspace(tmp_path)
    before = _client(root).get("/").text
    resolve_edition(root, "solo")
    after = _client(root).get("/").text
    assert after == before


# --- engineer -------------------------------------------------------------------


def test_engineer_mode_shows_task_ids_and_verbatim_states(tmp_path):
    root = _workspace(tmp_path)
    _fabricate_plan(root)
    page = _client(root, mode="engineer").get("/").text
    assert "Build internals" in page
    assert "<code>t1</code>" in page and "<code>t2</code>" in page
    assert "spec_blocked" in page  # the state as recorded, not a euphemism
    assert "avs retry-task" in page  # every button names its CLI equivalent


def test_engineer_mode_without_a_plan_says_so(tmp_path):
    page = _client(_workspace(tmp_path), mode="engineer").get("/").text
    assert "No plan yet" in page


def test_engineer_mode_shows_the_profile(tmp_path):
    root = _workspace(tmp_path, profile="miniprogram")
    page = _client(root, mode="engineer").get("/").text
    assert "<code>miniprogram</code>" in page


def test_engineer_edition_gets_engineer_mode_without_a_flag(tmp_path):
    root = _workspace(tmp_path)
    resolve_edition(root, "engineer")
    assert "Build internals" in _client(root).get("/").text


# --- enterprise -----------------------------------------------------------------


def test_enterprise_edition_shows_its_governance_facts(tmp_path):
    root = _workspace(tmp_path)
    resolve_edition(root, "enterprise")
    page = _client(root).get("/").text
    assert "Governance" in page
    assert "S2" in page  # substrate rung from the resolved edition
    assert "Every gate requires a named owner." in page
    assert "PL5" in page  # the never-consolidate floor is visible
    assert "No attestation ledger yet" in page  # absence stated, not omitted


def test_enterprise_attestation_count_is_read_from_the_ledger(tmp_path):
    root = _workspace(tmp_path)
    resolve_edition(root, "enterprise")
    ledger = root / ".mas" / "attestation" / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text('{"a":1}\n{"a":2}\n{"a":3}\n', encoding="utf-8")
    page = _client(root).get("/").text
    assert "Attestation ledger entries" in page and "<b>3</b>" in page


def test_enterprise_mode_without_an_edition_says_how_to_get_one(tmp_path):
    page = _client(_workspace(tmp_path), mode="enterprise").get("/").text
    assert "avs init --edition enterprise" in page


def test_enterprise_governance_reflects_the_file_not_a_cache(tmp_path):
    root = _workspace(tmp_path)
    resolve_edition(root, "enterprise")
    client = _client(root)
    assert "S2" in client.get("/").text
    path = root / ".mas" / "edition.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["defaults"]["substrate_rung"] = "S1"  # narrowing edit — still lints
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    assert "S1" in client.get("/").text


# --- the mode contract ----------------------------------------------------------


def test_modes_only_add_every_founder_action_survives(tmp_path):
    """The UI analogue of narrowing-never-widening: every form action and
    link the founder page renders must be present in every other mode, in
    every page state we can fabricate."""
    root = _workspace(tmp_path)
    _fabricate_plan(root)
    (root / "product" / "BUILD-REPORT.md").write_text("# done", encoding="utf-8")
    founder = _client(root).get("/").text
    actions = set(re.findall(r"(?:action|href)=['\"]?(/[a-z/]*)", founder))
    assert actions  # the report page has forms; an empty set would test nothing
    for mode in ("engineer", "enterprise"):
        page = _client(root, mode=mode).get("/").text
        missing = {a for a in actions if a not in page}
        assert not missing, f"{mode} mode dropped {sorted(missing)}"


def test_zh_engineer_panel_renders_in_chinese(tmp_path):
    root = _workspace(tmp_path)
    page = _client(root, mode="engineer", lang="zh").get("/").text
    assert "构建内幕" in page


def test_en_mode_pages_stay_free_of_cjk(tmp_path):
    """The v0.53 rule survives modes: the English UI has no CJK anywhere,
    including the new cards."""
    root = _workspace(tmp_path)
    resolve_edition(root, "enterprise")
    _fabricate_plan(root)
    for mode in ("engineer", "enterprise"):
        page = _client(root, mode=mode).get("/").text
        assert not re.search(r"[一-鿿]", page), f"{mode} mode leaks CJK"
