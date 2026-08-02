"""Try it — the built product beside its own acceptance list.

The report page says what was built. The founder's actual question is
whether it is right, and answering that means using the thing with the
criteria in front of you. This is that page: how to run it and the
screenshots on the left, the acceptance and verification rows on the
right, one honest verb each.

What the tests hold down: the product is never faked, a tick is founder
input rather than a verdict about the product, and a complaint carries the
criterion it came from so the router is not left guessing.
"""

from __future__ import annotations

import shutil

import pytest
import yaml
from fastapi.testclient import TestClient

from ai_venture_studio.studio import create_studio_app
from ai_venture_studio.studio_try import acceptance_rows, load_ticks
from ai_venture_studio.upstream import init_workspace

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)

ACCEPTANCE = (
    "# Acceptance walkthrough\n\n"
    "First run `avs preview`.\n\n"
    "- [ ] Add a task called Buy milk and see it in the open list\n"
    "- [ ] Mark it done and see it move to the done list\n"
)
VERIFICATION = (
    "# Automated verification\n\n"
    "- ✅ root-responds\n"
    "- ❌ items-listed — 500 from /items\n"
)


@pytest.fixture
def built(tmp_path):
    root = init_workspace(tmp_path / "try", "try", "web")
    product = root / "product"
    product.mkdir(exist_ok=True)
    (product / "BUILD-REPORT.md").write_text("# done", encoding="utf-8")
    (product / "ACCEPTANCE.md").write_text(ACCEPTANCE, encoding="utf-8")
    (product / "VERIFICATION.md").write_text(VERIFICATION, encoding="utf-8")
    client = TestClient(
        create_studio_app(root, spawn=lambda r: 1, provider="mock")
    )
    return client, root


# ── the rows, derived and never authored ─────────────────────────────────


def test_rows_come_from_the_artifacts_the_build_already_wrote(built):
    _client, root = built
    rows = acceptance_rows(root)
    texts = [row.text for row in rows]

    assert "Add a task called Buy milk and see it in the open list" in texts
    assert "root-responds" in texts
    assert {row.source for row in rows} == {"acceptance", "verification"}
    # Prose around the checkboxes is not a criterion.
    assert not any("First run" in text for text in texts)


def test_a_row_id_is_content_addressed(built):
    """A re-run that keeps a criterion keeps its tick; one that rewords it
    gets a fresh row rather than inheriting a tick for words nobody read."""
    _client, root = built
    before = {row.text: row.id for row in acceptance_rows(root)}
    (root / "product" / "ACCEPTANCE.md").write_text(
        ACCEPTANCE + "- [ ] Something entirely new\n", encoding="utf-8"
    )
    after = {row.text: row.id for row in acceptance_rows(root)}
    for text, row_id in before.items():
        assert after[text] == row_id


def test_the_page_shows_the_product_and_the_criteria_side_by_side(built):
    client, _root = built
    page = client.get("/try").text
    assert "The product" in page
    assert "What it was supposed to do" in page
    assert "Add a task called Buy milk" in page
    assert "root-responds" in page


def test_the_report_page_links_to_it(built):
    client, _root = built
    assert "href='/try'" in client.get("/").text


# ── never fake a running product ─────────────────────────────────────────


def test_it_names_the_command_instead_of_faking_a_running_product(built):
    client, root = built
    (root / "app").mkdir(exist_ok=True)
    (root / "app" / "main.py").write_text("print('hi')\n", encoding="utf-8")

    page = client.get("/try").text

    assert "avs preview" in page
    assert "app/main.py" in page
    assert "<iframe" not in page, "a frame pretending to hold the product"


def test_with_no_entry_point_it_says_so(built):
    client, _root = built
    page = client.get("/try").text
    assert "No runnable entry point" in page
    assert "<iframe" not in page


def test_the_screenshots_the_build_took_stand_in_for_the_frame(built):
    client, root = built
    shots = root / "product" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    (shots / "home.png").write_bytes(b"\x89PNG\r\n")

    page = client.get("/try").text
    assert "src='/shots/home.png'" in page


def test_a_miniprogram_gets_its_own_instruction(tmp_path):
    root = init_workspace(tmp_path / "mp", "mp", "miniprogram")
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "ACCEPTANCE.md").write_text(ACCEPTANCE, encoding="utf-8")
    client = TestClient(create_studio_app(root, provider="mock"))
    page = client.get("/try").text
    assert "WeChat DevTools" in page


# ── ticks: founder input, explicitly not a verdict ───────────────────────


def test_a_tick_persists_in_the_workspace_as_founder_input(built):
    client, root = built
    row = acceptance_rows(root)[0]

    client.post("/try/tick", data={"row": row.id}, follow_redirects=False)

    ticks = load_ticks(root)
    assert row.id in ticks
    assert ticks[row.id]["row"] == row.text
    # …and it is in the workspace, where every other fact lives.
    written = (root / "product" / "try-checks.yaml").read_text(encoding="utf-8")
    assert "NOT a verdict" in written
    assert yaml.safe_load(written)["checked"][row.id]["row"] == row.text


def test_the_page_says_a_tick_changes_nothing(built):
    client, _root = built
    page = client.get("/try").text
    assert "not a verdict about the product" in page
    assert "Nothing changes until you press the fix button" in page


def test_a_tick_changes_nothing_about_the_product(built):
    client, root = built
    row = acceptance_rows(root)[0]
    before = (root / "product" / "BUILD-REPORT.md").read_text(encoding="utf-8")
    acceptance_before = (root / "product" / "ACCEPTANCE.md").read_text(
        encoding="utf-8"
    )

    client.post("/try/tick", data={"row": row.id}, follow_redirects=True)

    assert (root / "product" / "BUILD-REPORT.md").read_text(encoding="utf-8") == before
    assert (root / "product" / "ACCEPTANCE.md").read_text(
        encoding="utf-8"
    ) == acceptance_before


def test_a_tick_can_be_taken_back(built):
    client, root = built
    row = acceptance_rows(root)[0]
    client.post("/try/tick", data={"row": row.id}, follow_redirects=True)
    page = client.post("/try/tick", data={"row": row.id, "off": "1"},
                       follow_redirects=True).text
    assert load_ticks(root) == {}
    assert "undo this tick" not in page


def test_a_ticked_row_stops_offering_fine_and_wrong(built):
    client, root = built
    row = acceptance_rows(root)[0]
    page = client.post("/try/tick", data={"row": row.id},
                       follow_redirects=True).text
    # The ticked row renders as FINE with an undo, and the OTHER rows still
    # carry both verbs.
    assert "undo this tick" in page
    assert "1 of 4 checked by you" in page


def test_a_row_id_that_is_not_a_row_is_refused_not_guessed(built):
    client, root = built
    for evil in ("../../etc/passwd", "a b; rm -rf /", "x" * 200):
        response = client.post("/try/tick", data={"row": evil},
                               follow_redirects=False)
        assert response.status_code < 500
    assert load_ticks(root) == {}

    page = client.post("/try/tick", data={"row": "abc123abc123"}).text
    assert "abc123abc123" in page and "no row" in page.lower()


# ── the complaint carries its criterion ──────────────────────────────────


def test_wrong_sends_the_row_text_with_the_complaint(built):
    client, _root = built
    page = client.get("/try").text
    assert "action=/correct" in page
    assert (
        "name=criterion value='Mark it done and see it move to the done list'"
        in page
    )


def test_the_router_is_told_which_criterion_failed(built, monkeypatch):
    """The point of carrying the row: the router that has to pick one spec
    out of many should not be left inferring which one from a sentence
    like "it never moved"."""
    import ai_venture_studio.upstream.correction as correction

    seen = {}
    original = correction.route_complaint

    def spy(root, complaint, **kwargs):
        seen.update(complaint=complaint, criterion=kwargs.get("criterion", ""))
        raise correction.CorrectionRouteError("nothing built yet")

    monkeypatch.setattr(correction, "route_complaint", spy)
    client, _root = built
    client.post("/correct", data={
        "complaint": "it never moved",
        "criterion": "Mark it done and see it move to the done list",
    }, follow_redirects=True)
    correction.route_complaint = original

    assert seen["complaint"] == "it never moved"
    assert seen["criterion"] == "Mark it done and see it move to the done list"


def test_the_page_survives_a_workspace_with_no_criteria_at_all(tmp_path):
    root = init_workspace(tmp_path / "bare", "bare", "web")
    client = TestClient(create_studio_app(root, provider="mock"))
    page = client.get("/try").text
    assert "No criteria yet" in page
