"""Large requests must stream, or nothing can be built.

The SDK computes an expected duration from max_tokens and REFUSES a
non-streaming call that could run past 10 minutes — it raises before
sending. The implementer asks for 32000 tokens (it returns whole files, and
16384 truncated real builds), so every build call died on

    ValueError: Streaming is required for operations that may take longer
    than 10 minutes

and `avs create` could not build a single task. Found only by reading the
detached worker's build.log after a run that looked "interrupted".
"""
from __future__ import annotations

import pytest

from ai_venture_studio.providers import anthropic_provider
from ai_venture_studio.providers.anthropic_provider import (
    _STREAM_ABOVE,
    AnthropicProvider,
)


class _Usage:
    input_tokens = 11
    output_tokens = 22


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Message:
    stop_reason = "end_turn"
    usage = _Usage()

    def __init__(self, text="hi"):
        self.content = [_Block(text)]


class _Stream:
    def __init__(self, recorder):
        self._recorder = recorder

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return _Message("streamed")


class _Messages:
    def __init__(self, recorder):
        self._recorder = recorder

    def create(self, **kwargs):
        self._recorder.append(("create", kwargs["max_tokens"]))
        return _Message("created")

    def stream(self, **kwargs):
        self._recorder.append(("stream", kwargs["max_tokens"]))
        return _Stream(self._recorder)


class _Client:
    def __init__(self, recorder):
        self.messages = _Messages(recorder)


@pytest.fixture
def calls(monkeypatch):
    recorded: list[tuple[str, int]] = []
    monkeypatch.setattr(
        anthropic_provider, "_make_client", lambda: _Client(recorded)
    )
    return recorded


def _chat(max_tokens):
    return AnthropicProvider().chat(
        model="claude-opus-4-8", system="s",
        messages=[{"role": "user", "content": "u"}], max_tokens=max_tokens,
    )


def test_the_implementer_sized_request_streams(calls):
    """32000 is the size that could not be sent at all."""
    assert _chat(32000) == "streamed"
    assert calls == [("stream", 32000)]


def test_small_requests_still_use_the_plain_call(calls):
    """Streaming everything would be a needless change to every voter,
    verifier and writer in the system."""
    assert _chat(1024) == "created"
    assert calls == [("create", 1024)]


def test_the_threshold_is_below_the_implementer_cap():
    from ai_venture_studio.upstream.build import _IMPLEMENTER_MAX_TOKENS

    assert _STREAM_ABOVE < _IMPLEMENTER_MAX_TOKENS, (
        "the implementer's own cap must land on the streaming path"
    )


def test_the_boundary_is_exclusive(calls):
    _chat(_STREAM_ABOVE)
    _chat(_STREAM_ABOVE + 1)
    assert [kind for kind, _ in calls] == ["create", "stream"]


def test_streaming_still_meters_and_records_the_stop_reason(calls, monkeypatch):
    """Spend accounting and truncation detection both hang off the final
    message. A streaming path that dropped them would break the cost gate
    and the cut-off guards silently."""
    from ai_venture_studio import spend
    from ai_venture_studio.providers import base

    recorded: list[tuple] = []
    monkeypatch.setattr(
        spend, "record",
        lambda model, inp, out, **kw: recorded.append((model, inp, out)),
    )

    _chat(32000)

    assert recorded == [("claude-opus-4-8", 11, 22)]
    assert base.last_stop_reason() == "end_turn"


# ── transient-failure budget ─────────────────────────────────────────────
# A 529 on one voter killed a build eleven minutes in: four attempts with
# 2/4/8s backoff spend the whole allowance in fourteen seconds, and a real
# overload event lasts far longer than that.

def test_the_retry_budget_is_worth_more_than_fourteen_seconds():
    from ai_venture_studio.providers.anthropic_provider import (
        _BACKOFF_CAP_S,
        _TRANSIENT_ATTEMPTS,
        _backoff_seconds,
    )

    total = sum(_backoff_seconds(i) for i in range(_TRANSIENT_ATTEMPTS - 1))
    assert _TRANSIENT_ATTEMPTS >= 6
    assert total > 60, f"only {total:.0f}s of patience for an overload"
    assert all(_backoff_seconds(i) <= _BACKOFF_CAP_S + 1 for i in range(20))


def test_a_retry_after_header_wins_over_our_exponent():
    from ai_venture_studio.providers.anthropic_provider import _backoff_seconds

    class _Resp:
        headers = {"retry-after": "7"}

    class _Exc(Exception):
        response = _Resp()

    assert _backoff_seconds(0, _Exc()) == 7.0


def test_a_junk_retry_after_falls_back_instead_of_crashing():
    from ai_venture_studio.providers.anthropic_provider import _backoff_seconds

    class _Resp:
        headers = {"retry-after": "soon-ish"}

    class _Exc(Exception):
        response = _Resp()

    assert _backoff_seconds(0, _Exc()) >= 2.0


def test_backoff_is_jittered_so_pooled_voters_do_not_retry_in_lockstep():
    from ai_venture_studio.providers.anthropic_provider import _backoff_seconds

    waits = {_backoff_seconds(1) for _ in range(20)}
    assert len(waits) > 1, "identical waits mean every voter retries together"


def test_a_transient_error_is_retried_then_succeeds(calls, monkeypatch):
    """The behaviour that matters: one 529 must not end the run."""
    import anthropic

    from ai_venture_studio.providers import anthropic_provider as ap

    monkeypatch.setattr(ap, "_backoff_seconds", lambda *a, **k: 0.0)
    import httpx

    boom = anthropic.OverloadedError(
        "overloaded",
        response=httpx.Response(
            529, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        ),
        body=None,
    )
    state = {"n": 0}
    real_create = _Messages.create

    def flaky(self, **kwargs):
        state["n"] += 1
        if state["n"] == 1:
            raise boom
        return real_create(self, **kwargs)

    monkeypatch.setattr(_Messages, "create", flaky)
    assert _chat(1024) == "created"
    assert state["n"] == 2, "the first 529 should have been retried"
