"""What every adapter owes its callers, checked for all of them at once.

Twelve real defects in one day, none caught by the suite. Two of them were
at the provider boundary, and the expensive one — a large `max_tokens`
making the SDK refuse the request before sending — shipped to PyPI twice
while 1441 tests stayed green.

The lesson is not "write more mocks". A mock is written by the same person
holding the same wrong belief about the SDK, so it agrees with the bug.
What a hermetic test CAN do is pin the invariants every adapter must hold
whatever the SDK does, so an adapter cannot quietly stop metering or stop
reporting truncation. The part that needs a real key is `avs smoke`, and
these tests pin its logic without spending anything.
"""

from __future__ import annotations

import pytest

from ai_venture_studio import smoke as smoke_mod
from ai_venture_studio.providers import ProviderError, get_provider
from ai_venture_studio.providers.base import (
    TRUNCATION_REASONS,
    last_response_truncated,
    record_stop_reason,
)

ADAPTERS = ["anthropic", "openai", "google", "xai", "mock"]


@pytest.mark.parametrize("name", ADAPTERS)
def test_every_adapter_has_the_same_call_shape(name):
    """One `chat(model, system, messages, max_tokens)` contract: the voter,
    the writer and the implementer all call it the same way."""
    import inspect

    signature = inspect.signature(get_provider(name).chat)
    assert set(signature.parameters) >= {"model", "system", "messages", "max_tokens"}
    for parameter in signature.parameters.values():
        if parameter.name != "self":
            assert parameter.kind is parameter.KEYWORD_ONLY, (
                "positional args let a caller pass system where model goes"
            )


@pytest.mark.parametrize("name", ["anthropic", "openai", "google", "xai"])
def test_an_unconfigured_adapter_raises_provider_error(name, monkeypatch):
    """Never a KeyError, never a silent empty answer: ProviderError is what
    the voter loop catches to fall back to a declared substitute."""
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY",
                "GOOGLE_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv(f"{var}_FILE", raising=False)
    monkeypatch.delenv("AVS_ANTHROPIC_MODE", raising=False)

    with pytest.raises(ProviderError):
        get_provider(name).chat(
            model="whatever", system="s", messages=[{"role": "user", "content": "u"}]
        )


def test_truncation_vocabulary_covers_every_adapter_dialect():
    """anthropic says max_tokens, OpenAI-compatible bodies say length, and
    Gemini says MAX_TOKENS. Miss one and the build loop writes half a file
    believing it got a whole one."""
    assert {"max_tokens", "length", "MAX_TOKENS"} <= TRUNCATION_REASONS


def test_stop_reason_is_thread_local():
    """Voters run in a thread pool; a module global would report one
    thread's truncation to another."""
    import threading

    record_stop_reason("end_turn")
    seen = {}

    def other():
        record_stop_reason("max_tokens")
        seen["other"] = last_response_truncated()

    thread = threading.Thread(target=other)
    thread.start()
    thread.join()

    assert seen["other"] is True
    assert last_response_truncated() is False, "the other thread's cap leaked"


# --- the smoke's own logic, checked without spending anything --------------


class _Fake:
    """A provider that behaves the way the real SDK does at each boundary."""

    def __init__(self, *, empty=False, raises_on_large=False, records_stop=True,
                 meters=True, unconfigured=False):
        self.empty = empty
        self.raises_on_large = raises_on_large
        self.records_stop = records_stop
        self.meters = meters
        self.unconfigured = unconfigured

    def chat(self, *, model, system, messages, max_tokens=4096):
        if self.unconfigured:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        if self.raises_on_large and max_tokens > 8192:
            # The verbatim shape of the v0.62.0 failure.
            raise ValueError(
                "Streaming is required for operations that may take longer "
                "than 10 minutes"
            )
        record_stop_reason("max_tokens" if (self.records_stop and max_tokens <= 16)
                           else "end_turn")
        if self.meters:
            from ai_venture_studio import spend

            spend.record(model, 5, 5)
        return "" if self.empty else "ready"


def _run(monkeypatch, fake):
    monkeypatch.setattr(smoke_mod, "get_provider", lambda name: fake)
    return smoke_mod.smoke_provider("anthropic")


def test_a_healthy_provider_passes_every_check(monkeypatch):
    result = _run(monkeypatch, _Fake())
    assert result.status == "ok", [c.model_dump() for c in result.checks]
    assert {c.name for c in result.checks} == {
        "reachable", "streams_large", "truncation_visible", "usage_metered"
    }


def test_the_bug_that_shipped_twice_is_caught(monkeypatch):
    """A large max_tokens raising before send = `avs create` builds nothing.
    v0.60.0 and v0.61.0 went to PyPI in exactly this state."""
    result = _run(monkeypatch, _Fake(raises_on_large=True))

    assert result.status == "failed"
    failed = result.failed[0]
    assert failed.name == "streams_large"
    assert "build nothing at all" in failed.detail


def test_a_missing_key_is_a_skip_not_a_pass_and_not_a_failure(monkeypatch):
    result = _run(monkeypatch, _Fake(unconfigured=True))

    assert result.status == "skipped"
    assert "ANTHROPIC_API_KEY" in result.checks[0].detail
    assert len(result.checks) == 1, "one missing key should not be reported four times"


def test_an_empty_response_is_a_failure(monkeypatch):
    """The shape that reached voters as a silent BLOCKED."""
    result = _run(monkeypatch, _Fake(empty=True))

    assert result.status == "failed"
    assert "empty" in result.failed[0].detail


def test_an_adapter_that_stops_reporting_truncation_fails(monkeypatch):
    result = _run(monkeypatch, _Fake(records_stop=False))

    assert result.status == "failed"
    assert "truncation_visible" in [c.name for c in result.failed]
    assert "partial files reach disk" in result.failed[0].detail


def test_an_adapter_that_stops_metering_fails(monkeypatch):
    """The cost gate and the founder's cost line both read that ledger; a
    silent zero is the number nobody questions."""
    result = _run(monkeypatch, _Fake(meters=False))

    assert result.status == "failed"
    assert "usage_metered" in [c.name for c in result.failed]


def test_smoke_defaults_name_real_current_models():
    """A smoke pointed at a retired model id fails for the wrong reason."""
    assert smoke_mod.DEFAULT_MODELS["anthropic"].startswith("claude-")
    assert set(smoke_mod.DEFAULT_MODELS) >= {"anthropic", "openai", "google"}


def test_a_null_content_from_a_reasoning_model_is_an_empty_string(monkeypatch):
    """gpt-5 at a small cap answers with `content: null` and
    finish_reason=length — it spent the whole budget reasoning. Every caller
    does `raw.strip()`, so a None reached the voter's generic retry as an
    AttributeError about attributes rather than about budget.

    Measured on the first live run of `avs smoke`: max_tokens=16 → empty,
    stop=length; 512 and up → "ready", stop=stop.
    """
    import httpx

    from ai_venture_studio.providers import openai_compat

    class _Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "choices": [
                    {"message": {"role": "assistant", "content": None},
                     "finish_reason": "length"}
                ],
                "usage": {"prompt_tokens": 9, "completion_tokens": 16},
            }

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Response())

    text = openai_compat.OpenAIProvider().chat(
        model="gpt-5", system="s", messages=[{"role": "user", "content": "u"}],
        max_tokens=16,
    )

    assert text == ""
    assert last_response_truncated(), "length must still read as truncated"


def test_the_smoke_uses_a_budget_a_real_caller_would_use():
    """A 16-token cap is not a configuration this system ever ships; testing
    it made the smoke report a working provider as broken."""
    assert smoke_mod._REALISTIC_MIN_TOKENS >= 512
