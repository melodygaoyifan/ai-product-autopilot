"""The analytics/feedback privacy boundary, metric vocabulary, cohorts,
signal routing, Gate PL4 — the v2.3.0 evidence gate's structural half.

The gate's own words (§23 week P6): "an agent request for individual rows
returns an error (tested, not documented); a cohort under the floor
returns a refusal; a metric cited without a definition file fails."
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from autoproduct.evidence import (
    AnalyticsStore,
    CohortTooSmallError,
    FeedbackStore,
    MetricDefinition,
    OutcomeReason,
    PersonLevelQueryError,
    Signal,
    cohort_calc,
    comparison_issues,
    gate_pl4,
    load_metric_vocabulary,
    metric_definition_check,
    pii_scan,
    route_signal,
    sample_sufficiency_check,
)
from autoproduct.product import synthetic_persona_scan

FIXTURES = Path(__file__).parent / "fixtures" / "evidence"
REPO_METRICS = Path(__file__).parent.parent / "metrics"
TODAY = dt.date(2026, 7, 26)


def _events(cohorts: dict[str, int], hits: dict[str, int]) -> list[dict]:
    events = []
    for week, n in cohorts.items():
        for i in range(n):
            unit = f"{week}-u{i}"
            events.append({"unit": unit, "signup_week": week, "event": "workspace.created"})
            if i < hits.get(week, 0):
                events.append(
                    {"unit": unit, "signup_week": week, "event": "workspace.first_export"}
                )
    return events


# --- the query-layer refusals (invariant 14.16) ------------------------------


def test_person_level_query_returns_an_error():
    store = AnalyticsStore(_events({"w1": 30}, {"w1": 10}))
    with pytest.raises(PersonLevelQueryError, match="14.16"):
        store.cohort_aggregate(group_by=["user_id"], numerator_event="x")
    with pytest.raises(PersonLevelQueryError):
        store.cohort_aggregate(
            group_by=["signup_week"], numerator_event="x", where={"email": "a@b.c"}
        )
    with pytest.raises(PersonLevelQueryError):
        store.cohort_aggregate(
            group_by=["signup_week"], numerator_event="x", distinct_field="device_id"
        )


def test_cohort_under_the_floor_is_refused():
    store = AnalyticsStore(_events({"w1": 30, "w2": 5}, {}))
    with pytest.raises(CohortTooSmallError, match="n=5"):
        store.cohort_aggregate(
            group_by=["signup_week"], numerator_event="workspace.first_export"
        )


def test_floor_is_configurable_upward_only():
    with pytest.raises(PersonLevelQueryError, match="upward"):
        AnalyticsStore([], min_cohort_size=5)
    AnalyticsStore([], min_cohort_size=50)  # raising is fine


def test_free_text_is_redacted_before_egress():
    store = AnalyticsStore(
        [
            {
                "kind": "churn_reason",
                "text": "too pricey, ping me at dana@corp.example or 555-201-3344",
            }
        ]
    )
    (text,) = store.free_text(kind="churn_reason")
    assert "dana@corp.example" not in text and "555-201-3344" not in text
    assert "[email redacted]" in text and "[phone redacted]" in text


# --- feedback provenance (ADR-U23 wiring) ------------------------------------


def test_feedback_locators_resolve_and_quotes_are_redacted(tmp_path):
    store = FeedbackStore(tmp_path)
    artifact = store.ingest(
        '"I lose two hours every week stitching CSV exports together by hand" '
        "— from ticket by sam@buyer.example",
        kind="ticket",
        source_id="support-tickets",
    )
    assert store.resolve(artifact.locator) is not None
    assert "sam@buyer.example" not in artifact.text_redacted
    assert store.cluster_counts("stitching CSV exports") == {"ticket": 1}
    # The stored raw artifact is what makes the quote real for persona_scan.
    quote_in_prose = (
        '"I lose two hours every week stitching CSV exports together by hand," '
        "says a recruiting ops lead."
    )
    assert synthetic_persona_scan(quote_in_prose, tmp_path) == []


# --- metric vocabulary (§22.62.3-.4) ------------------------------------------


def test_repo_metric_vocabulary_loads_and_undefined_metric_fails():
    vocabulary = load_metric_vocabulary(REPO_METRICS)
    assert "activation_rate" in vocabulary
    issues = metric_definition_check(["activation_rate", "vibes_score"], vocabulary)
    assert [(i.metric_id, i.rule) for i in issues] == [("vibes_score", "undefined_metric")]


def test_definition_change_resets_the_baseline():
    metric = MetricDefinition(
        id="activation_rate", definition="…", changed_at="2026-06-14"
    )
    assert comparison_issues(metric, dt.date(2026, 6, 20), dt.date(2026, 7, 20)) == []
    issues = comparison_issues(metric, dt.date(2026, 6, 1), dt.date(2026, 7, 20))
    assert [i.rule for i in issues] == ["definition_change_break"]


# --- cohort readings and sufficiency (§22.62.2) -------------------------------


def _metric() -> MetricDefinition:
    return MetricDefinition(
        id="activation_rate",
        definition="share of new workspaces exporting within 7 days",
        numerator_event="workspace.first_export",
        window_days=7,
        cohort_basis="signup_week",
    )


def test_cohort_calc_reads_through_the_boundary():
    store = AnalyticsStore(_events({"w1": 40, "w2": 50}, {"w1": 10, "w2": 20}))
    readings = cohort_calc(
        store,
        _metric(),
        cohort_field="signup_week",
        cohort_start=dt.date(2026, 7, 1),
        today=TODAY,
    )
    by_week = {r.cohort["signup_week"]: r for r in readings}
    assert by_week["w1"].n == 40 and by_week["w1"].value == 0.25
    assert by_week["w1"].ci_low < 0.25 < by_week["w1"].ci_high
    assert by_week["w1"].window_complete  # July 1 + 7d has elapsed by July 26
    assert by_week["w1"].source_type == "primary_measured"


def test_incomplete_window_is_marked():
    store = AnalyticsStore(_events({"w1": 40}, {"w1": 10}))
    (reading,) = cohort_calc(
        store,
        _metric(),
        cohort_field="signup_week",
        cohort_start=dt.date(2026, 7, 22),  # day 4 of a 7-day window
        today=TODAY,
    )
    assert not reading.window_complete


def test_a_verdict_on_n6_is_not_a_verdict():
    verdict = sample_sufficiency_check(n=6, baseline=0.11, mde_relative=0.5)
    assert not verdict.sufficient
    assert verdict.required_n > 6
    assert "what it would take" not in verdict.message  # message states the n itself
    assert f"required n={verdict.required_n}" in verdict.message
    big = sample_sufficiency_check(n=100_000, baseline=0.11, mde_relative=0.5)
    assert big.sufficient


# --- signal router fixture gate (§22.62.1) ------------------------------------


def _router_fixtures():
    doc = yaml.safe_load((FIXTURES / "router.yaml").read_text())
    return doc["fixtures"]


@pytest.mark.parametrize("fixture", _router_fixtures(), ids=lambda f: f["label"])
def test_signal_router_fixture(fixture):
    routing = route_signal(Signal(**fixture["input"]))
    assert routing.destination == fixture["expect"]["destination"], routing.reason


def test_router_fixture_gate_is_the_standing_eight():
    assert len(_router_fixtures()) == 8


# --- Gate PL4 (§22.62.2) --------------------------------------------------------


def test_gate_pl4_demands_a_reading_or_a_reason():
    result = gate_pl4(["O-1", "O-2"], readings={}, reasons=[], ledger_issue_count=0)
    assert not result.passed and result.missing_outcomes == ["O-1", "O-2"]

    reasons = [
        OutcomeReason(
            outcome_id="O-2",
            reason="insufficient_evidence",
            detail="needs n=1,213 per cohort at the stated 15% relative effect",
        )
    ]
    store = AnalyticsStore(_events({"w1": 40}, {"w1": 10}))
    (reading,) = cohort_calc(
        store, _metric(), cohort_field="signup_week",
        cohort_start=dt.date(2026, 7, 1), today=TODAY,
    )
    result = gate_pl4(["O-1", "O-2"], {"O-1": reading}, reasons, ledger_issue_count=0)
    assert result.passed

    dirty = gate_pl4(["O-1"], {"O-1": reading}, [], ledger_issue_count=2)
    assert not dirty.passed and dirty.ledger_issues == 2


def test_gate_pl4_reasons_are_typed_and_substantive():
    with pytest.raises(ValueError, match="one of"):
        OutcomeReason(outcome_id="O-1", reason="we forgot", detail="…")
    with pytest.raises(ValueError, match="silence"):
        OutcomeReason(outcome_id="O-1", reason="window_incomplete", detail="  ")


def test_pii_scan_is_shared_and_total():
    assert pii_scan("ssn 123-45-6789") == "ssn [ssn redacted]"
