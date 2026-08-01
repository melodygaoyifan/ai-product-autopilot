"""The spend card: cost visibility where money is decided — never a gate.

The founder signal asked to SEE the number ("how much will a typical month
of builds cost me? I'm scared to leave autopilot running"), so the card
shows spend on the confirm page (before the first dollar) and the report
page, honestly floor-labelled when a call has no price on file.

Deliberately absent, by decision (ADR-032): a cap, a ceiling form, any
refusal. Every call is billed to the founder's own key or subscription, so
spending limits belong to the provider account that does the billing. A
framework-side dollar cap existed for one release (v0.66) and was removed —
these tests pin its absence as firmly as its presence was pinned before.

Sibling surface: VERIFICATION.md — the founder's own requirements probed
against the built product — is served and linked, because a verification
nobody can see persuades nobody.
"""

import shutil

import pytest
from fastapi.testclient import TestClient

from ai_venture_studio import spend
from ai_venture_studio.prices import import_into_workspace
from ai_venture_studio.studio import create_studio_app
from ai_venture_studio.upstream import init_workspace

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)


@pytest.fixture
def studio(tmp_path):
    root = init_workspace(tmp_path / "prod", "prod", "web")
    client = TestClient(
        create_studio_app(root, spawn=lambda r: 4242, provider="mock")
    )
    return client, root


def _built_product(root) -> None:
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "BUILD-REPORT.md").write_text("# done\n", encoding="utf-8")


def test_the_card_shows_spend_and_whose_money_it_is(studio):
    client, root = studio
    _built_product(root)
    import_into_workspace(root)
    spend.record("claude-opus-4-8", 1_000_000, 100_000)  # $5 + $2.50
    spend.flush(root)

    page = client.get("/").text

    assert "What this cost" in page
    assert "$7.50" in page
    assert "your own API key" in page


def test_the_card_shows_before_the_first_dollar(studio):
    """"No spend yet" is itself an answer to "I'm scared to leave autopilot
    running" — the empty state is where the founder learns the number lives."""
    client, root = studio
    _built_product(root)

    page = client.get("/").text

    assert "What this cost" in page
    assert "No model calls yet this month" in page


def test_the_card_sits_on_the_confirm_page_where_spend_is_decided(studio):
    client, root = studio
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "CONFIRMATION.md").write_text("plan\n", encoding="utf-8")

    page = client.get("/").text

    assert "Confirm the plan" in page
    assert "What this cost" in page


def test_the_floor_is_labelled_when_a_call_is_unpriced(studio):
    client, root = studio
    _built_product(root)
    import_into_workspace(root)
    spend.record("grok-4", 10_000, 1_000)  # deliberately unpriced
    spend.flush(root)

    page = client.get("/").text

    assert "≥$" in page
    assert "floor" in page


def test_there_is_no_cap_no_ceiling_form_and_no_refusal(studio):
    """ADR-032, pinned: the cap was removed. No form posts a ceiling, no
    copy warns about one, and a heavy month renders the same plain card."""
    client, root = studio
    _built_product(root)
    import_into_workspace(root)
    spend.record("claude-opus-4-8", 100_000_000, 10_000_000)  # a huge month
    spend.flush(root)

    page = client.get("/").text

    assert "action=/cap" not in page
    assert "cap" not in page.lower().replace("capture", "")
    assert "paused" not in page.lower()
    assert client.post("/cap", data={"cap": "20"}).status_code in (404, 405)


def test_modes_deepen_the_card_without_changing_the_founders(studio):
    client, root = studio
    _built_product(root)
    import_into_workspace(root)
    spend.record("claude-opus-4-8", 50_000, 5_000)
    spend.flush(root)

    founder = client.get("/?mode=founder").text
    engineer = client.get("/?mode=engineer").text

    for page in (founder, engineer):
        assert "What this cost" in page  # the plain card survives everywhere
    assert "Per-model spend" in engineer
    assert "avs prices --import" in engineer  # CLI twin, engineer only
    assert "Per-model spend" not in founder


def test_verification_is_linked_and_served_when_it_exists(studio):
    client, root = studio
    _built_product(root)

    assert "verification" not in client.get("/").text.lower()

    (root / "product" / "VERIFICATION.md").write_text(
        "# 验收 / Verification\n- [x] create works\n", encoding="utf-8"
    )
    home = client.get("/").text
    assert "What was checked automatically" in home

    served = client.get("/verification").text
    assert "create works" in served
