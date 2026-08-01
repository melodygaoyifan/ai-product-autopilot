"""EARS accepts a bare subject; the article was never the requirement.

Found in a live run: four criteria of the shape

    When fetchFn rejects and a cached list exists, loadCatalog shall
    return source equal to 'cache' ...

were rejected for "does not match any EARS pattern". They are well-formed
event-driven requirements — trigger, subject, shall, response — that happen
to name a function rather than "the system". The task was blocked, the
module never built, and writing "the loadCatalog shall" to satisfy the
regex would have been worse English than the original.
"""
from __future__ import annotations

import pytest

from ai_venture_studio.upstream.ears import classify, lint_criteria

# The exact strings from the blocked spec.
FROM_THE_LIVE_RUN = [
    "When fetchFn resolves with at least one valid record, loadCatalog shall "
    "return source equal to 'live' with the normalized items.",
    "When fetchFn rejects and a cached list exists in the store, loadCatalog "
    "shall return source equal to 'cache' with the cached items.",
]


@pytest.mark.parametrize("criterion", FROM_THE_LIVE_RUN)
def test_the_criteria_that_blocked_a_real_task_now_pass(criterion):
    assert lint_criteria([criterion]) == []
    assert classify(criterion) == "event"


@pytest.mark.parametrize(
    "criterion, kind",
    [
        ("The system shall persist the cart.", "ubiquitous"),
        ("loadCatalog shall return a normalized list.", "ubiquitous"),
        ("When the fetch fails, the system shall serve the cache.", "event"),
        ("When the fetch fails, cacheStore shall serve the last list.", "event"),
        ("While a build runs, the page shall poll for progress.", "state"),
        ("While a build runs, statusPoller shall refresh every 4 seconds.", "state"),
        ("If the payload is malformed, then the API shall return 400.", "unwanted"),
        ("If the payload is malformed, then handler shall return 400.", "unwanted"),
        ("Where sharing is enabled, the app shall render a QR code.", "optional"),
        ("Where sharing is enabled, shareCard shall render a QR code.", "optional"),
    ],
)
def test_both_articled_and_bare_subjects_classify_the_same(criterion, kind):
    assert classify(criterion) == kind
    assert lint_criteria([criterion]) == []


@pytest.mark.parametrize(
    "criterion",
    [
        "The app should be fast.",                      # vague + no shall
        "Make the list load nicely.",                   # no structure at all
        "shall return a list",                          # no subject
        "The system will return a list.",               # 'will', not 'shall'
    ],
)
def test_structureless_criteria_are_still_rejected(criterion):
    assert lint_criteria([criterion]), f"should have been rejected: {criterion}"


def test_relaxing_the_article_did_not_make_prose_a_requirement():
    """The ubiquitous pattern is the risky one — with no leading keyword,
    dropping the article naively would match almost any sentence."""
    prose = "We shall see whether the founders like it."
    assert classify(prose) == "invalid"
    assert lint_criteria([prose])


def test_vague_terms_are_still_caught_on_an_otherwise_valid_criterion():
    issues = lint_criteria(["loadCatalog shall return results quickly."])
    assert any("vague" in i.problem for i in issues)


@pytest.mark.parametrize(
    "criterion",
    [
        "loadCatalog shall return a normalized list.",   # camelCase
        "fetch_data shall retry twice.",                 # snake_case
        "api.handler shall return 400 on bad input.",    # dotted
    ],
)
def test_identifier_subjects_are_the_ones_allowed_bare(criterion):
    assert classify(criterion) == "ubiquitous"


@pytest.mark.parametrize(
    "criterion",
    [
        "We shall see whether the founders like it.",
        "It shall be decided later.",
        "This shall depend on the reviewer.",
        "Users shall be happy.",
    ],
)
def test_ordinary_english_subjects_still_need_their_article(criterion):
    """Otherwise the lint stops being a grammar and starts being a
    word-search for 'shall'."""
    assert classify(criterion) == "invalid"
    assert lint_criteria([criterion])


# ── the connective is optional too ───────────────────────────────────────
# Found on a retry: the article fix unblocked the task, the writer rephrased
# the next draft as "If X, the system shall Y" — no "then" — and the
# unwanted pattern rejected it. Same pedantry, second helping.

@pytest.mark.parametrize(
    "criterion",
    [
        "If httpGet is unusable and readCache rejects, the system shall "
        "return an empty result without throwing.",
        "If the payload is malformed, the API shall return 400.",
        "If the payload is malformed, then the API shall return 400.",
        "If the cache is cold, loadCatalog shall fetch from the network.",
    ],
)
def test_if_criteria_pass_with_or_without_then(criterion):
    assert classify(criterion) == "unwanted"
    assert lint_criteria([criterion]) == []


def test_if_still_needs_a_shall():
    assert lint_criteria(["If the payload is malformed, the API returns 400."])
