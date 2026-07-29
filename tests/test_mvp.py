"""The MVP contract: is a first slice minimum AND viable?

The system already reduced scope in four places. What it had nowhere was the
question that separates an MVP from a small build — does this slice, on its
own, tell us whether the thing is worth building? Doc 13 §29 specified
exactly that rule ("every MVP-tier hypothesis must be validatable by the
MVP-tier increments alone") and it was never implemented.

The AI delta encodes what practitioners converge on as non-skippable for an
AI feature, none of which is about model quality: a named simpler
alternative, a declared cost of being wrong, a wrong-answer fallback, an eval
set written first, and a quality metric paired to every volume metric.
"""

from __future__ import annotations

import pytest

from ai_venture_studio.product.mvp import (
    MIN_EVAL_CASES,
    MVP_TIER,
    AIFeature,
    MVPSlice,
    ai_mvp_lint,
    detect_ai_feature,
    gate_mvp_entry,
    mvp_lint,
)


def _good_slice(**overrides) -> MVPSlice:
    base = {
        "hypothesis": "founders cannot tell whether a long build is progressing",
        "increments": ["a per-task progress panel on the building page"],
        "success_signal": "3 of 3 reporters confirm it resolves the uncertainty",
        "not_now": ["dark mode", "shareable links"],
        "cheapest_test": "show the 3 reporters a clickable mockup",
    }
    return MVPSlice(**{**base, **overrides})


# --- minimum AND viable ------------------------------------------------------


def test_a_well_formed_slice_passes():
    assert mvp_lint(_good_slice()) == []


def test_the_rule_doc_13_specified_and_nobody_implemented():
    """A hypothesis about one thing and increments about another: the slice
    cannot settle its own question, so building it learns nothing."""
    findings = mvp_lint(_good_slice(
        hypothesis="shoppers will pay more for same-day delivery",
        increments=["a dark mode toggle in settings"],
    ))
    assert [f.rule for f in findings] == ["hypothesis_not_validatable_by_slice"]


def test_morphology_does_not_produce_a_false_positive():
    """"progressing" vs "progress", "build" vs "building" — comparing whole
    words made these disagree and flagged a slice that was well matched. A
    check that cries wolf on good input gets ignored on bad input."""
    for hypothesis, increment in [
        ("founders cannot tell if the build is progressing", "a progress panel"),
        ("teams lose track of finished work", "mark a task finished"),
        ("users abandon long uploads", "an upload progress bar"),
    ]:
        findings = mvp_lint(_good_slice(
            hypothesis=hypothesis, increments=[increment]
        ))
        assert [f.rule for f in findings] == [], f"false positive on {hypothesis!r}"


def test_a_chinese_slice_is_matched_on_characters_not_latin_words():
    """A Chinese FDR has no [a-z] words at all; word matching would silently
    pass everything, including a genuine mismatch."""
    matched = mvp_lint(_good_slice(
        hypothesis="团长看不到接龙的汇总",
        increments=["按商品汇总的页面"],
        success_signal="一周有 10 个团长用过",
    ))
    assert [f.rule for f in matched] == []

    mismatched = mvp_lint(_good_slice(
        hypothesis="团长看不到接龙的汇总",
        increments=["深色模式开关"],
        success_signal="一周有 10 个团长用过",
    ))
    assert "hypothesis_not_validatable_by_slice" in [f.rule for f in mismatched]


def test_a_slice_with_nothing_user_visible_cannot_validate_anything():
    findings = mvp_lint(_good_slice(increments=[]))
    rules = [f.rule for f in findings]
    assert "no_user_visible_increment" in rules


def test_success_must_be_countable():
    assert "unmeasurable_success_signal" in [
        f.rule for f in mvp_lint(_good_slice(success_signal="users love it"))
    ]
    assert "no_success_signal" in [
        f.rule for f in mvp_lint(_good_slice(success_signal="   "))
    ]
    # a number, or a countable noun, is enough
    for ok in ("10 founders come back", "the rate of stuck reports drops"):
        assert mvp_lint(_good_slice(success_signal=ok)) == []


def test_a_slice_that_defers_nothing_is_not_a_slice():
    """Canon calls an empty out-of-scope list a smell; the schema had let it
    default to empty."""
    assert "nothing_deferred" in [
        f.rule for f in mvp_lint(_good_slice(not_now=[]))
    ]


def test_build_it_and_see_is_not_a_cheapest_test():
    """The same term of art P0's Falsifiability voter polices, now checked
    deterministically."""
    for bad in ("build the MVP and see", "just build it", "implement the feature"):
        assert "cheapest_test_is_the_build" in [
            f.rule for f in mvp_lint(_good_slice(cheapest_test=bad))
        ], bad
    assert mvp_lint(_good_slice(
        cheapest_test="show 3 reporters a mockup and count confirmations"
    )) == []


def test_wider_tiers_are_not_held_to_first_slice_rules():
    """A standard or deep plan is not claiming to be a first slice, so these
    rules would be noise there."""
    empty = MVPSlice()
    assert mvp_lint(empty, scope_tier="standard") == []
    assert mvp_lint(empty, scope_tier="deep") == []
    assert mvp_lint(empty, scope_tier=MVP_TIER) != []


# --- the AI delta ------------------------------------------------------------


def _good_feature(**overrides) -> AIFeature:
    base = {
        "capability": "summarize the ticket into one line",
        "why_not_deterministic": "a keyword rule missed 40% of real tickets",
        "cost_of_being_wrong": "recoverable",
        "fallback_behavior": "below confidence, show the raw ticket and say why",
        "autonomy_rung": "suggest",
        "eval_cases": MIN_EVAL_CASES,
        "volume_metric": "tickets summarized",
        "quality_metric": "edit rate on the summary",
    }
    return AIFeature(**{**base, **overrides})


def test_a_well_formed_ai_feature_passes():
    assert ai_mvp_lint(_good_feature()) == []


def test_a_simpler_alternative_must_be_named():
    """The strongest published guidance points the same way: often the honest
    MVP is a form."""
    assert "no_simpler_alternative_considered" in [
        f.rule for f in ai_mvp_lint(_good_feature(why_not_deterministic=""))
    ]


def test_the_cost_of_being_wrong_must_be_declared_from_the_enum():
    assert "cost_of_being_wrong_undeclared" in [
        f.rule for f in ai_mvp_lint(_good_feature(cost_of_being_wrong=""))
    ]
    assert "cost_of_being_wrong_undeclared" in [
        f.rule for f in ai_mvp_lint(_good_feature(cost_of_being_wrong="a bit bad"))
    ]


def test_an_irreversible_mistake_may_not_act_at_mvp():
    rules = [f.rule for f in ai_mvp_lint(
        _good_feature(cost_of_being_wrong="irreversible")
    )]
    assert "irreversible_at_mvp" in rules


def test_autonomy_may_not_exceed_the_cost_of_being_wrong():
    rules = [f.rule for f in ai_mvp_lint(_good_feature(
        cost_of_being_wrong="expensive", autonomy_rung="autonomous"
    ))]
    assert "autonomy_exceeds_cost_of_being_wrong" in rules
    # the same cost is fine when it only suggests
    assert ai_mvp_lint(_good_feature(
        cost_of_being_wrong="expensive", autonomy_rung="suggest"
    )) == []


def test_an_unknown_autonomy_rung_is_refused():
    assert "unknown_autonomy_rung" in [
        f.rule for f in ai_mvp_lint(_good_feature(autonomy_rung="full-send"))
    ]


def test_a_wrong_answer_path_is_mandatory():
    assert "no_fallback_behavior" in [
        f.rule for f in ai_mvp_lint(_good_feature(fallback_behavior=""))
    ]


def test_the_eval_set_has_a_floor():
    assert "eval_set_too_small" in [
        f.rule for f in ai_mvp_lint(_good_feature(eval_cases=3))
    ]
    assert ai_mvp_lint(_good_feature(eval_cases=MIN_EVAL_CASES)) == []


def test_every_volume_metric_needs_a_paired_quality_metric():
    """Deflection without confirmed resolution looks like success for months
    while quality drops."""
    assert "volume_metric_without_quality_metric" in [
        f.rule for f in ai_mvp_lint(_good_feature(quality_metric=""))
    ]
    # a quality metric with no volume metric is not the failure mode
    assert ai_mvp_lint(_good_feature(volume_metric="")) == []


def test_ai_rules_apply_at_every_tier():
    """The reasons an AI feature needs a fallback do not weaken because the
    scope got wider."""
    bare = AIFeature()
    for tier in ("thin", "standard", "deep"):
        assert ai_mvp_lint(bare, scope_tier=tier) != []


# --- detection ---------------------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("we want an AI assistant for billing", True),
    ("a chatbot that answers questions", True),
    ("summarize each ticket into one line", True),
    ("recommend products the shopper might like", True),
    ("智能推荐相似的商品", True),
    ("a form to add a task with a title", False),
    ("show open and finished tasks separately", False),
])
def test_ai_shaped_slices_are_detected_from_the_founders_own_words(text, expected):
    assert bool(detect_ai_feature(text)) is expected


def test_detection_quotes_the_phrase_that_fired_it():
    """Explainable by construction: a founder who disagrees can see why the
    extra obligations appeared."""
    trigger = detect_ai_feature("add a copilot to the editor")
    assert trigger.lower() == "copilot"


# --- the gate surface --------------------------------------------------------


def test_the_gate_records_why_not_only_that():
    result = gate_mvp_entry(_good_slice(), _good_feature())
    assert result["passed"] is True
    assert result["ai_feature"] is True
    assert result["findings"] == []

    blocked = gate_mvp_entry(_good_slice(not_now=[]), AIFeature())
    assert blocked["passed"] is False
    rules = {f["rule"] for f in blocked["findings"]}
    assert "nothing_deferred" in rules
    assert "no_fallback_behavior" in rules  # both linters contribute


def test_a_slice_with_no_ai_feature_is_not_held_to_ai_rules():
    result = gate_mvp_entry(_good_slice())
    assert result["passed"] is True
    assert result["ai_feature"] is False
