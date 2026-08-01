"""The spend guard: cost AND the ceiling, where money is decided.

The research on non-technical builders is unambiguous: surprise bills are a
top fear ($607 Replit bills, credits burned in debugging loops), every
usage-billed platform is implicated, none set a spending cap by default,
and the universally recommended fix is a hard cap on day one. This repo HAS
the cap — and it shipped CLI-only, so the founder, the one persona that
cannot be asked to use a CLI, saw a cost card with no ceiling on it.

These tests pin the Studio surface: the card shows the cap state, sets it
in one click into the same .mas/cost-model.yaml the CLI owns, appears on
the confirm page (where the spend is decided) as well as the report page
(where the bill exists), and deepens per mode without ever changing the
founder's plain card. Plus the sibling gap: VERIFICATION.md — the founder's
own requirements run against what was built — was written to disk and never
linked; a verification nobody can see persuades nobody.
"""

import shutil

import pytest
from fastapi.testclient import TestClient

from ai_venture_studio import spend
from ai_venture_studio.observability import load_cost_model
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


def test_no_cap_shows_the_warning_and_the_one_click_form(studio):
    client, root = studio
    _built_product(root)

    page = client.get("/").text

    assert "Spending &amp; cap" in page
    assert "Surprise bills" in page
    assert "action=/cap" in page
    assert "Set monthly cap" in page


def test_setting_the_cap_writes_the_cli_owned_file_with_prices(studio):
    """One click = a cap that can actually FIRE: the packaged reference
    prices ride along, because a cap compared against an unpriced floor
    never bites."""
    client, root = studio
    _built_product(root)

    done = client.post("/cap", data={"cap": "25"}, follow_redirects=False)

    assert done.status_code == 303
    model = load_cost_model(root / ".mas")
    assert model.monthly_cap_usd == 25.0
    assert model.prices, "prices imported so the cap is comparable to real spend"

    page = client.get("/").text
    assert "of your $25.00 cap" in page
    assert "Change the cap" in page


def test_an_operator_corrected_price_survives_the_studio_button(studio):
    client, root = studio
    (root / ".mas" / "cost-model.yaml").write_text(
        "prices:\n  claude-opus-4-8:\n    input: 2.5\n    output: 12.5\n"
        "monthly_cap_usd: 0\n",
        encoding="utf-8",
    )

    client.post("/cap", data={"cap": "40"}, follow_redirects=False)

    assert load_cost_model(root / ".mas").prices["claude-opus-4-8"]["input"] == 2.5


def test_over_the_cap_says_paused_not_broken(studio):
    """The gate stopping a build is the cap WORKING — the card must say
    'paused, raise to continue', never read as a failure."""
    client, root = studio
    _built_product(root)
    import_into_workspace(root, cap_usd=1.0)
    spend.record("claude-opus-4-8", 1_000_000, 100_000)  # far over $1
    spend.flush(root)

    page = client.get("/").text

    assert "builds are paused between modules" in page.lower() or "paused" in page
    assert "Nothing is lost" in page


def test_the_floor_is_labelled_when_a_call_is_unpriced(studio):
    client, root = studio
    _built_product(root)
    import_into_workspace(root, cap_usd=50.0)
    spend.record("grok-4", 10_000, 1_000)  # deliberately unpriced
    spend.flush(root)

    page = client.get("/").text

    assert "≥$" in page
    assert "floor" in page


def test_the_card_sits_on_the_confirm_page_where_spend_is_decided(studio):
    client, root = studio
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "CONFIRMATION.md").write_text("plan\n", encoding="utf-8")

    page = client.get("/").text

    assert "Confirm the plan" in page
    assert "Spending &amp; cap" in page
    assert "action=/cap" in page


def test_modes_deepen_the_card_without_changing_the_founders(studio):
    client, root = studio
    _built_product(root)
    import_into_workspace(root, cap_usd=30.0)
    spend.record("claude-opus-4-8", 50_000, 5_000)
    spend.flush(root)

    founder = client.get("/?mode=founder").text
    engineer = client.get("/?mode=engineer").text
    enterprise = client.get("/?mode=enterprise").text

    for page in (founder, engineer, enterprise):
        assert "Spending &amp; cap" in page  # the plain card survives everywhere
    assert "avs prices --import" in engineer  # CLI twin, engineer only
    assert "avs prices --import" not in founder
    assert "Per-model spend" in engineer
    assert "cost-model.yaml" in enterprise  # governance note, enterprise only
    assert "cost-model.yaml" not in founder


def test_garbage_cap_input_changes_nothing(studio):
    client, root = studio

    page = client.post("/cap", data={"cap": "twenty dollars"})

    assert "not a valid amount" in page.text
    assert not (root / ".mas" / "cost-model.yaml").exists()


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
