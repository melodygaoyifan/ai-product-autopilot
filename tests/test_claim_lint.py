"""claim_lint against the seeded fabrication fixtures (§23 weeks P1-P2).

The v2.1.0 substrate gate: 8/8 seeded fixtures caught, each firing exactly
the rule it was hand-labeled with, and zero false positives on the clean
control. Tests pin today to 2026-07-26 so the expired-evidence fixture is
deterministic.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from autoproduct.product import (
    ProductPolicy,
    ProductPolicyError,
    ledger_class_for,
    lint_ledger,
    load_product_policy,
    source_types_for,
    store_snapshot,
    synthetic_persona_scan,
)
from autoproduct.upstream.discover import EVIDENCE_CLASSES

FABRICATION = Path(__file__).parent / "fixtures" / "fabrication"
TODAY = dt.date(2026, 7, 26)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _fixture_paths() -> list[Path]:
    return sorted(FABRICATION.glob("*.yaml"))


def test_fixture_set_is_complete():
    fixtures = [_load(p) for p in _fixture_paths()]
    planted = [f for f in fixtures if f["expect"]["rule"]]
    assert len(planted) == 8, "the seeded fabrication set is 8 fixtures"
    assert any(f["expect"]["rule"] is None for f in fixtures), "clean control present"


@pytest.mark.parametrize(
    "path",
    [p for p in _fixture_paths() if _load(p)["expect"]["checker"] == "claim_lint"],
    ids=lambda p: p.stem,
)
def test_claim_lint_fixtures_fire_exactly_their_labeled_rule(path):
    fixture = _load(path)
    issues = lint_ledger(fixture, fixture["kind"], today=TODAY)
    fired = {issue.rule for issue in issues}
    expected = fixture["expect"]["rule"]
    if expected is None:
        assert fired == set(), f"clean control produced false positives: {fired}"
    else:
        assert fired == {expected}, (
            f"{path.stem}: planted exactly {expected!r}, fired {fired}"
        )


def test_synthetic_testimonial_caught_by_persona_scan(tmp_path):
    fixture = _load(FABRICATION / "05-synthetic-testimonial.yaml")
    findings = synthetic_persona_scan(fixture["artifact_text"], tmp_path)
    assert [f.rule for f in findings] == ["synthetic_testimonial"]
    # The ledger itself is well-formed — that is why the companion scan exists.
    assert lint_ledger(fixture, fixture["kind"], today=TODAY) == []


def test_quote_resolving_to_stored_artifact_passes(tmp_path):
    fixture = _load(FABRICATION / "05-synthetic-testimonial.yaml")
    ticket = (
        "Ticket #4411: \"I lose two hours every week stitching CSV exports "
        "together by hand,\" reported by customer during churn review."
    )
    store_snapshot(ticket.encode(), tmp_path, suffix=".txt")
    assert synthetic_persona_scan(fixture["artifact_text"], tmp_path) == []


def test_clean_control_is_clean_for_the_whole_substrate(tmp_path):
    fixture = _load(FABRICATION / "00-clean-control.yaml")
    assert lint_ledger(fixture, fixture["kind"], today=TODAY) == []
    assert synthetic_persona_scan(fixture.get("artifact_text", ""), tmp_path) == []


def test_inference_ceiling_is_tunable_but_never_removable(tmp_path):
    fixture = _load(FABRICATION / "07-inference-over-ceiling.yaml")
    (tmp_path / "product-policy.yaml").write_text(
        "inference_ceilings:\n  market: 0.7\n"
    )
    policy = load_product_policy(tmp_path)
    assert lint_ledger(fixture, "market", today=TODAY, policy=policy) == []
    # The requirement itself is not tunable: a ceiling outside (0, 1] is rejected.
    (tmp_path / "product-policy.yaml").write_text(
        "inference_ceilings:\n  market: 1.5\n"
    )
    with pytest.raises(ProductPolicyError):
        load_product_policy(tmp_path)


def test_absent_policy_file_means_shipped_defaults(tmp_path):
    policy = load_product_policy(tmp_path)
    assert policy == ProductPolicy()
    assert policy.ceiling_for("market") == 0.30
    assert policy.ceiling_for("unknown-kind") == 0.30


def test_empty_ledger_is_a_finding():
    issues = lint_ledger({"claims": []}, "market", today=TODAY)
    assert [i.rule for i in issues] == ["empty_ledger"]


def test_bad_source_type_is_a_finding():
    doc = {"claims": [{"id": "C-1", "text": "x", "source_type": "vibes"}]}
    issues = lint_ledger(doc, "market", today=TODAY)
    assert "bad_source_type" in {i.rule for i in issues}


def test_hypothesis_class_mapping_is_bidirectional_and_matches_discovery():
    # §20.53.6 — the claim schema refines measured/sourced/assumed; the
    # mapping must round-trip and cover exactly Discovery's classes.
    assert set(EVIDENCE_CLASSES) == {"measured", "sourced", "assumed"}
    for ledger_class in EVIDENCE_CLASSES:
        for source_type in source_types_for(ledger_class):
            assert ledger_class_for(source_type) == ledger_class
    with pytest.raises(ValueError):
        ledger_class_for("vibes")
    with pytest.raises(ValueError):
        source_types_for("hunch")
