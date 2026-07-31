"""The failure page must say what actually happened.

Regression cover for two shipped defects found while inspecting a real
founder-visible failure:

1. `_failure_page` rendered one hardcoded cause — "a missing or exhausted
   model API key" — for every exception. A transient provider overload on a
   valid, funded key therefore read as a billing problem.
2. `failed_hint` was defined TWICE in studio_i18n.STRINGS. Python keeps the
   last definition, so the "Modules that did not build" card (the common
   partial-build path) silently rendered the error page's key text.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from ai_venture_studio import studio, studio_i18n
from ai_venture_studio.studio_i18n import STRINGS, t


class _Overloaded(Exception):
    pass


class _Auth(Exception):
    pass


@pytest.mark.parametrize(
    "exc, expected",
    [
        (_Auth("ANTHROPIC_API_KEY is not set"), "key"),
        (_Auth("Error code: 401 - authentication_error"), "key"),
        (_Auth("Your credit balance is too low to access the API"), "key"),
        (_Overloaded("Error code: 529 - overloaded_error"), "busy"),
        (_Overloaded("Error code: 429 - rate_limit_error"), "busy"),
        (_Overloaded("Connection error."), "busy"),
        (_Overloaded("Request timed out"), "busy"),
        (ValueError("writer failed schema after 3 attempts"), "unknown"),
        (RuntimeError("something nobody predicted"), "unknown"),
    ],
)
def test_the_cause_is_read_from_the_exception(exc, expected):
    assert studio.failure_cause(exc) == expected


def test_an_overload_is_never_reported_as_a_key_problem():
    """The exact defect: a 529 on a good key must not send the founder to
    their billing page."""
    cause = studio.failure_cause(_Overloaded("Error code: 529 - overloaded_error"))
    assert cause == "busy"
    for lang in ("en", "zh"):
        text = t(lang, f"failed_cause_{cause}")
        assert "API key" not in text
        assert "API key" not in text.replace("api key", "API key")


def test_every_cause_has_a_string_in_every_language():
    for cause in ("key", "busy", "unknown"):
        for lang in studio_i18n.LANGUAGES:
            assert t(lang, f"failed_cause_{cause}").strip()


def test_the_unknown_cause_does_not_invent_one():
    """'unknown' must point at the detail, not name a suspect."""
    text = t("en", "failed_cause_unknown").lower()
    assert "not certain" in text
    assert "api key" not in text


def test_the_failed_modules_card_no_longer_uses_the_error_page_string():
    """The duplicate-key collision: this card is about modules, not keys."""
    modules_hint = t("en", "failed_modules_hint")
    assert "the rest of the product works" in modules_hint
    assert "API key" not in modules_hint
    assert "failed_hint" not in STRINGS  # the colliding key is gone entirely


def test_no_duplicate_keys_in_the_string_table():
    """The collision was invisible at runtime — a dict literal silently keeps
    the last definition — so it has to be caught in the SOURCE."""
    source = pathlib.Path(studio_i18n.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    tables = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign | ast.Assign)
        and isinstance(node.value, ast.Dict)
    ]
    assert tables, "expected at least one dict literal (STRINGS) in studio_i18n"
    duplicates: list[str] = []
    for table in tables:
        seen: set[str] = set()
        for key in table.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value in seen:
                    duplicates.append(key.value)
                seen.add(key.value)
    assert not duplicates, f"duplicate string keys silently shadowed: {duplicates}"


def test_the_failure_is_recorded_for_the_operator(tmp_path):
    """Rendering to the browser and nowhere else left no record once the tab
    was closed."""
    try:
        raise _Overloaded("Error code: 529 - overloaded_error")
    except _Overloaded as exc:
        studio.record_failure(tmp_path, exc)

    ledger = tmp_path / ".mas" / "studio-failures.jsonl"
    entry = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert entry["cause"] == "busy"
    assert "529" in entry["error"]
    assert "_Overloaded" in entry["traceback"]
    assert entry["at"].endswith("+00:00")


def test_recording_never_breaks_the_page(tmp_path):
    """An unwritable workspace must not turn a handled failure into a 500."""
    blocked = tmp_path / "wall"
    blocked.write_text("not a directory", encoding="utf-8")
    studio.record_failure(blocked, _Overloaded("boom"))  # must not raise
