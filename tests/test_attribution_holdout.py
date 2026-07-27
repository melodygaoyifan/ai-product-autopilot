"""Attribution typing at the tool boundary + holdout tooling (§22.63).

The v2.3.0 gate's attribution half: a claim that a channel "drove" signups
is rejected; the same observation restated as typed facts passes; a
holdout is the one path to a causal claim — proven end-to-end through
claim_lint, both enforcement layers on purpose (invariant 14.18).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from ai_venture_studio.evidence import (
    ATTRIBUTION_RULES,
    AttributionMethodError,
    ExposureLog,
    assign_geo_holdout,
    assign_holdout,
    attribute_claim,
    compare_holdout,
    type_observation,
)
from ai_venture_studio.product import lint_ledger

FIXTURES = Path(__file__).parent / "fixtures" / "evidence"
TODAY = dt.date(2026, 7, 26)


def _attribution_fixtures():
    doc = yaml.safe_load((FIXTURES / "attribution.yaml").read_text())
    return doc["fixtures"]


@pytest.mark.parametrize("fixture", _attribution_fixtures(), ids=lambda f: f["label"])
def test_attribution_fixture(fixture):
    result = attribute_claim(fixture["input"]["text"], fixture["input"]["method"])
    expect = fixture["expect"]
    if "rejected" in expect:
        assert isinstance(result, list), "expected a boundary rejection"
        assert [f.rule for f in result] == [expect["rejected"]]
    else:
        assert isinstance(result, dict), result
        assert result["source_type"] == expect["source_type"]


def test_attribution_fixture_gate_is_the_standing_eight():
    assert len(_attribution_fixtures()) == 8


def test_unknown_method_is_refused_not_defaulted():
    with pytest.raises(AttributionMethodError, match="typing table"):
        type_observation("best_available")


def test_only_holdouts_ground_causal_claims():
    causal_capable = {m for m, (_, causal) in ATTRIBUTION_RULES.items() if causal}
    assert causal_capable == {"holdout_experiment", "geo_holdout"}


def test_both_enforcement_layers_end_to_end():
    # Layer 1: the boundary rejects the causal claim over last-touch.
    rejected = attribute_claim("The launch post drove 40% of signups", "last_touch")
    assert isinstance(rejected, list)

    # Layer 2: had it been smuggled into a ledger anyway, claim_lint fires.
    smuggled = {
        "claims": [
            {
                "id": "C-X",
                "text": "The launch post drove 40% of signups",
                "source_type": "model_inference",
                "falsifier": "holdout shows no lift",
            }
        ]
    }
    rules = {i.rule for i in lint_ledger(smuggled, "evidence", today=TODAY)}
    assert "causal_without_experiment" in rules

    # And the legitimate path: a holdout-typed claim passes the same lint.
    accepted = attribute_claim(
        "The onboarding email drove a 6-point activation lift vs holdout",
        "holdout_experiment",
    )
    ledger = {
        "claims": [
            {
                **accepted,
                "id": "C-HOLD",
                "n": 1840,
                "evidence": [
                    {
                        "method": "holdout_experiment",
                        "locator": "experiments/EXP-2026-031",
                        "retrieved_at": "2026-07-25T09:00:00Z",
                    }
                ],
                "falsifier": "re-analysis of the same holdout shows CI overlap",
            }
        ]
    }
    assert lint_ledger(ledger, "evidence", today=TODAY) == []


# --- holdout tooling (§22.63.3) -----------------------------------------------


def test_holdout_assignment_is_deterministic_and_near_fraction():
    units = [f"u{i}" for i in range(2000)]
    first = assign_holdout(units, holdout_fraction=0.15, salt="EXP-2026-031")
    second = assign_holdout(units, holdout_fraction=0.15, salt="EXP-2026-031")
    assert first.holdout == second.holdout  # reproducible from the salt
    assert set(first.holdout) | set(first.exposed) == set(units)
    assert not set(first.holdout) & set(first.exposed)
    assert 0.10 <= len(first.holdout) / len(units) <= 0.20

    different_salt = assign_holdout(units, holdout_fraction=0.15, salt="EXP-2")
    assert different_salt.holdout != first.holdout


def test_holdout_assignment_requires_a_salt_and_sane_fraction():
    with pytest.raises(ValueError, match="auditable"):
        assign_holdout(["u1"], holdout_fraction=0.15, salt="")
    with pytest.raises(ValueError):
        assign_holdout(["u1"], holdout_fraction=1.5, salt="x")


def test_geo_holdout_splits_by_region():
    assignment = assign_geo_holdout(
        {"north": ["u1", "u2"], "south": ["u3"], "west": ["u4"]},
        holdout_regions=["south"],
    )
    assert assignment.holdout == ["u3"]
    assert assignment.method == "geo" and assignment.holdout_fraction == 0.25


def test_exposure_log_records_what_actually_happened():
    log = ExposureLog()
    log.log("u1", "exposed", "2026-07-20T10:00:00Z")
    log.log("u2", "holdout", "2026-07-20T10:00:01Z")
    assert log.units("exposed") == {"u1"} and len(log) == 2


def test_holdout_comparison_types_causal_and_reports_inconclusive_honestly():
    win = compare_holdout(
        exposed_hits=300, exposed_n=1000, holdout_hits=150, holdout_n=1000
    )
    assert win.conclusive and win.lift == pytest.approx(0.15)
    assert win.typed.may_ground_causal
    assert win.typed.source_type == "primary_measured"

    noise = compare_holdout(
        exposed_hits=52, exposed_n=500, holdout_hits=48, holdout_n=500
    )
    assert not noise.conclusive
    assert "inconclusive enters" in noise.detail.replace("\n", " ") or "nothing" in noise.detail

    with pytest.raises(ValueError, match="empty arm"):
        compare_holdout(exposed_hits=1, exposed_n=10, holdout_hits=0, holdout_n=0)
