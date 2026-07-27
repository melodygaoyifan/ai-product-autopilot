"""Phase B: profile + data voter families under the same 8-fixture
registration contract as the product voters (§11.19, plan items 8-9)."""

from __future__ import annotations

import pytest

from ai_venture_studio.product.stage_engine import load_voter_charters
from ai_venture_studio.product.voter_gate import (
    FAMILY_FIXTURES,
    FAMILY_SKILLS,
    family_roots,
    load_voter_fixtures,
)

EXPECTED = {
    "web": 3, "miniprogram": 1, "app": 1, "data": 3,
    # Upstream critique rosters (doc 13 §25.1, plan phase D13).
    "discovery": 4, "planning": 5, "spec": 5,
}


def _all_family_voters():
    return [
        pytest.param(family, path.stem, id=f"{family}/{path.stem}")
        for family in EXPECTED
        for path in sorted(FAMILY_FIXTURES[family].glob("*.yaml"))
    ]


def test_charter_fixture_bijection_per_family():
    for family, expected in EXPECTED.items():
        skills_root, _ = family_roots(family)
        charters = {n for n, _ in load_voter_charters(family, skills_root)}
        fixture_sets = {p.stem for p in FAMILY_FIXTURES[family].glob("*.yaml")}
        assert charters == fixture_sets, (family, charters ^ fixture_sets)
        assert len(charters) == expected, family


@pytest.mark.parametrize(("family", "voter"), _all_family_voters())
def test_family_fixture_sets_meet_the_standing_contract(family, voter):
    _, fixtures_root = family_roots(family)
    fixtures = load_voter_fixtures(family, voter, fixtures_root)
    assert len(fixtures) == 8
    for fixture in fixtures:
        if fixture.should_find:
            assert fixture.must_mention, f"{fixture.label}: positives name terms"


def test_product_stages_unaffected_by_family_roots():
    assert family_roots("opportunity") == (None, None)
    assert set(FAMILY_SKILLS) == set(FAMILY_FIXTURES) == set(EXPECTED)
