"""The cost cap can fire now (item 3).

`cost_gate` has been complete since v0.59.0 and inert ever since:
`CostModel.prices` defaults to empty, so every call was UNPRICED, the month's
total was reported as a floor, and a cap compared against a floor never bites.
2000+ calls were burned across workspaces in one day with a cap "configured"
and structurally unable to stop anything.

What was missing was not mechanism but evidence: the framework will not invent
a price. These tests pin the three properties that make a shipped price table
honest — sourced, ceiling-not-guess, and loud when stale — plus the one that
makes it safe to re-run: your corrections survive an import.
"""

import datetime as dt

import pytest
import yaml

from ai_venture_studio import spend
from ai_venture_studio.observability import load_cost_model
from ai_venture_studio.prices import (
    import_into_workspace,
    load_reference_prices,
    reference_path,
    unpriced_models,
)


def test_every_shipped_price_cites_a_source_and_a_date():
    """The same standard claim_lint applies to every other number here: a
    price with no locator is exactly the unsourced number the linter exists
    to reject."""
    prices = load_reference_prices()

    assert dt.date.fromisoformat(prices.retrieved_at)  # parses, or raises
    assert prices.entries, "a shipped table with no entries is the old bug"
    for entry in prices.entries:
        assert entry.provider in prices.sources, entry.model
        assert prices.sources[entry.provider].startswith("https://")
        assert entry.input > 0 and entry.output > 0


def test_the_table_ships_inside_the_package():
    """The v0.54.0 failure mode: data resolved relative to the repo root works
    in a checkout and is absent from the wheel."""
    path = reference_path()
    assert path.exists()
    assert path.parent.name == "ai_venture_studio"


def test_a_range_resolves_upward_so_the_estimate_is_a_ceiling():
    """A cap exists to stop spend, so under-counting is the failure that
    matters. Sonnet 5's introductory $2/$10 runs to 2026-08-31; the table
    carries the $3/$15 standard price and says why."""
    entries = {e.model: e for e in load_reference_prices().entries}

    sonnet = entries["claude-sonnet-5"]
    assert (sonnet.input, sonnet.output) == (3.0, 15.0)
    assert "introductory" in sonnet.note

    gemini = entries["gemini-3.1-pro"]
    assert (gemini.input, gemini.output) == (4.0, 18.0)
    assert "200k" in gemini.note


def test_a_stale_table_says_so():
    """Prices rot. An old table must announce itself rather than quietly
    costing a month at last quarter's rates."""
    prices = load_reference_prices()
    retrieved = dt.date.fromisoformat(prices.retrieved_at)

    assert prices.stale(retrieved + dt.timedelta(days=prices.stale_after_days + 1))
    assert not prices.stale(retrieved + dt.timedelta(days=1))


def test_import_makes_the_gate_able_to_fire(tmp_path):
    """The end-to-end property: before the import the month is unpriced and
    the cap cannot bite; after it, the same usage is refused."""
    root = tmp_path / "w"
    (root / ".mas").mkdir(parents=True)

    for _ in range(40):
        spend.record("claude-opus-4-8", 120_000, 12_000)
    spend.flush(root)

    (root / ".mas" / "cost-model.yaml").write_text(
        "monthly_cap_usd: 25.0\n", encoding="utf-8"
    )
    before = spend.cost_gate(root)
    assert before.passed, "no prices: nothing to compare, so nothing is refused"
    assert before.is_floor and before.spent_usd == 0.0

    import_into_workspace(root)

    after = spend.cost_gate(root)
    assert not after.passed
    assert after.spent_usd == pytest.approx(36.0)  # 4.8M in @ $5, 480k out @ $25
    assert not after.is_floor
    assert "$25.00 limit YOU set" in after.reasons[0]


def test_your_price_survives_an_import(tmp_path):
    """A negotiated rate or a correction must not be silently replaced by a
    list price the next time someone runs the import."""
    root = tmp_path / "w"
    (root / ".mas").mkdir(parents=True)
    (root / ".mas" / "cost-model.yaml").write_text(
        yaml.safe_dump({
            "prices": {"claude-opus-4-8": {"input": 2.5, "output": 12.5}},
            "monthly_cap_usd": 100.0,
        }),
        encoding="utf-8",
    )

    result = import_into_workspace(root)

    assert "claude-opus-4-8" in result.models_kept
    assert load_cost_model(root / ".mas").prices["claude-opus-4-8"]["input"] == 2.5
    assert result.cap_usd == 100.0, "importing prices is not changing the budget"

    # ...and --overwrite is the explicit way to refresh them.
    import_into_workspace(root, overwrite=True)
    assert load_cost_model(root / ".mas").prices["claude-opus-4-8"]["input"] == 5.0


def test_the_cap_is_only_set_when_asked(tmp_path):
    root = tmp_path / "w"
    root.mkdir()

    plain = import_into_workspace(root)
    assert plain.cap_usd == 0.0, "0 means not configured, stated not silent"

    with_cap = import_into_workspace(root, cap_usd=40.0)
    assert with_cap.cap_usd == 40.0
    assert load_cost_model(root / ".mas").monthly_cap_usd == 40.0


def test_an_unpriced_model_is_named_not_hidden(tmp_path):
    """grok-4 is deliberately absent from the table — no list price was
    sourced, and a number nobody can cite is worse than a visible gap."""
    root = tmp_path / "w"
    (root / ".mas").mkdir(parents=True)
    spend.record("grok-4", 30_000, 900)
    spend.record("claude-opus-4-8", 1_000, 100)
    spend.flush(root)
    import_into_workspace(root, cap_usd=50.0)  # a cap, or the gate checks nothing

    assert unpriced_models(root) == ["grok-4"]

    gate = spend.cost_gate(root)
    assert gate.is_floor, "a total that hides an unpriced call understates"
    assert "FLOOR" in gate.note
    assert gate.passed, "under the cap — the floor is a caveat, not a refusal"
