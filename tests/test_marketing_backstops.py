"""The seven deterministic marketing backstops against their fixture gates.

The v2.2.0 release gate (§23 weeks P3-P5): every backstop fixture-gated at
>=87.5% — held here to the stronger bar of exact per-fixture agreement
(each fixture states the exact set of rules that must fire), with the
87.5% floor asserted explicitly so the release-gate number is a tested
fact rather than a README claim.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ai_venture_studio.marketing import (
    BrandConfig,
    ComplianceProfile,
    DeliverabilityConfig,
    Draft,
    EmailArtifact,
    Page,
    RegisteredClaim,
    ReleaseContract,
    SpamPolicyConfig,
    TrackedAsset,
    UtmTaxonomy,
    brand_and_safety_scan,
    check_substantiation,
    deliverability_preflight,
    disclosure_lint,
    geo_extractability_check,
    spam_policy_check,
    utm_and_instrumentation_lint,
)

MARKETING_FIXTURES = Path(__file__).parent / "fixtures" / "marketing"
BACKSTOPS = (
    "substantiation",
    "disclosure",
    "deliverability",
    "spam_policy",
    "brand_safety",
    "geo",
    "utm",
)
FIXTURE_GATE_FLOOR = 0.875  # §11.19 registration bar, applied to backstops


def _register(claims: list[dict]) -> ReleaseContract:
    return ReleaseContract(
        prd_ref="PRD-TEST",
        instrumentation_verified=True,
        claims_available=[RegisteredClaim(**c) for c in claims],
    )


def _run_backstop(name: str, inp: dict) -> set[str]:
    if name == "substantiation":
        findings = check_substantiation(
            inp["draft_text"], _register(inp["register"]), tol=inp.get("tol", 0.0)
        )
    elif name == "disclosure":
        findings = disclosure_lint(
            Draft(**inp["draft"]),
            ComplianceProfile(**inp.get("profile", {})),
            _register(inp["register"]) if inp.get("register") else None,
        )
    elif name == "deliverability":
        findings = deliverability_preflight(
            EmailArtifact(**inp["email"]),
            DeliverabilityConfig(**inp.get("config", {})),
        )
    elif name == "spam_policy":
        findings = spam_policy_check(
            [Page(**p) for p in inp["batch"]],
            already_published_this_period=inp.get("already_published_this_period", 0),
            config=SpamPolicyConfig(**inp.get("config", {})),
        )
    elif name == "brand_safety":
        findings = brand_and_safety_scan(
            Draft(**inp["draft"]),
            ComplianceProfile(**inp.get("profile", {})),
            BrandConfig(**inp.get("brand", {})),
        )
    elif name == "geo":
        findings = geo_extractability_check(Page(**inp["page"]))
    elif name == "utm":
        findings = utm_and_instrumentation_lint(
            [TrackedAsset(**a) for a in inp["assets"]],
            taxonomy=UtmTaxonomy(**inp["taxonomy"]) if inp.get("taxonomy") else None,
            analytics_events=set(inp.get("analytics_events", [])),
        )
    else:  # pragma: no cover
        raise ValueError(name)
    return {f.rule for f in findings}


def _fixtures(name: str) -> list[dict]:
    doc = yaml.safe_load((MARKETING_FIXTURES / f"{name}.yaml").read_text())
    return doc["fixtures"]


def _cases() -> list:
    return [
        pytest.param(name, fx, id=f"{name}:{fx['label']}")
        for name in BACKSTOPS
        for fx in _fixtures(name)
    ]


@pytest.mark.parametrize(("name", "fixture"), _cases())
def test_backstop_fixture_fires_exactly_its_labeled_rules(name, fixture):
    fired = _run_backstop(name, fixture["input"])
    expected = set(fixture["expect"]["rules"])
    assert fired == expected, (
        f"{name}/{fixture['label']}: expected exactly {sorted(expected)}, "
        f"fired {sorted(fired)}"
    )


@pytest.mark.parametrize("name", BACKSTOPS)
def test_backstop_fixture_gate_at_or_above_floor(name):
    fixtures = _fixtures(name)
    assert len(fixtures) == 8, "the standing fixture-gate contract is 8 per check"
    passed = sum(
        1
        for fx in fixtures
        if _run_backstop(name, fx["input"]) == set(fx["expect"]["rules"])
    )
    rate = passed / len(fixtures)
    assert rate >= FIXTURE_GATE_FLOOR, f"{name}: {passed}/8 below the 87.5% gate"
