"""The live-boundary smoke — the contract layer the hermetic suite cannot be.

Twelve real defects were found in one day of running this product against
one real FDR. The suite was green for every one of them, and it was right
to be: they lived at boundaries a mock does not model.

    v0.60.0, v0.61.0   shipped to PyPI unable to build a single task. The
                       implementer asks for 32000 output tokens; the SDK
                       computes an expected duration from max_tokens and
                       REFUSES a non-streaming request that might run past
                       ten minutes — raising before it sends anything.
                       1441 tests passed. Every real build died.

No amount of mocking finds that, because the mock is written by the same
person holding the same wrong belief about the SDK. Only a real call does.

So: four checks, each pinned to a class of failure that has actually
shipped, run against whichever providers are configured, costing a fraction
of a cent because every prompt is trivial and every cap is a ceiling rather
than a spend.

    reachable            a call returns text at all (key, base_url, model id)
    streams_large        max_tokens above the streaming threshold works —
                         THE v0.62.0 bug, which shipped twice
    truncation_visible   a response cut off at the cap is detectable, since
                         truncated YAML usually still parses and a partial
                         answer that parses is worse than one that does not
    usage_metered        the spend ledger saw the call, so `avs cost` and
                         the founder's cost line are not silently reading zero

An unconfigured provider is SKIPPED, loudly, naming the variable. A skip is
never a pass: "we did not check" and "it works" must not look alike.

This spends money on the caller's own key — a few tenths of a cent — and
prints what it spent. It is the one command in the system that makes a
model call for no reason other than to prove the wiring, which is exactly
why it belongs in the release checklist rather than in CI.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ai_venture_studio.providers import ProviderError, get_provider
from ai_venture_studio.providers.base import last_response_truncated

#: Cheap, current models — the smoke proves the WIRING, and the wiring does
#: not care which model answers. Override with --model when you want to
#: prove a specific seat.
DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-5",
    "google": "gemini-3.1-pro",
    "xai": "grok-4",
}

#: Above this the anthropic adapter must switch to streaming. Asking for a
#: big ceiling costs nothing: billing follows the tokens actually produced,
#: and the prompt below asks for one word.
_BIG_MAX_TOKENS = 16384

#: The smallest budget any real caller passes. Measured, not guessed: the
#: first run of this smoke used 16 and gpt-5 answered with an empty string
#: and finish_reason=length, because a reasoning model spends its budget on
#: reasoning before it writes anything (512 and up answer "ready" normally).
#: Reporting that as a broken provider would have been the smoke lying about
#: a configuration no caller uses — voters and writers ask for 1024 to 32000.
_REALISTIC_MIN_TOKENS = 512


class Check(BaseModel):
    name: str
    status: str  # ok | failed | skipped
    detail: str = ""


class ProviderSmoke(BaseModel):
    provider: str
    model: str
    status: str  # ok | failed | skipped
    checks: list[Check] = Field(default_factory=list)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == "failed"]


def run_smoke(
    providers: list[str] | None = None, *, model: str | None = None
) -> list[ProviderSmoke]:
    return [
        smoke_provider(name, model=model)
        for name in (providers or ["anthropic", "openai", "google"])
    ]


def smoke_provider(name: str, *, model: str | None = None) -> ProviderSmoke:
    chosen = model or DEFAULT_MODELS.get(name, "")
    result = ProviderSmoke(provider=name, model=chosen, status="ok")
    try:
        provider = get_provider(name)
    except Exception as exc:  # noqa: BLE001 — an unknown provider is a skip
        return ProviderSmoke(
            provider=name, model=chosen, status="skipped",
            checks=[Check(name="registry", status="skipped", detail=str(exc)[:200])],
        )

    for check in (_reachable, _streams_large, _truncation_visible, _usage_metered):
        outcome = check(provider, chosen)
        result.checks.append(outcome)
        if outcome.status == "skipped" and outcome.name == "reachable":
            # Not configured: the remaining checks would report the same
            # missing key three more times.
            result.status = "skipped"
            return result
        if outcome.status == "failed":
            result.status = "failed"
    return result


def _reachable(provider, model: str) -> Check:
    try:
        text = provider.chat(
            model=model,
            system="Answer with exactly one word.",
            messages=[{"role": "user", "content": "Say: ready"}],
            max_tokens=_REALISTIC_MIN_TOKENS,
        )
    except ProviderError as exc:
        # A missing credential is the expected state on most machines.
        return Check(name="reachable", status="skipped", detail=str(exc)[:300])
    except Exception as exc:  # noqa: BLE001 — the point is to see real errors
        return Check(
            name="reachable", status="failed",
            detail=f"{type(exc).__name__}: {str(exc)[:300]}",
        )
    if not text.strip():
        return Check(
            name="reachable", status="failed",
            detail="the call succeeded and returned an empty string — the "
                   "shape that used to reach voters as a silent BLOCKED",
        )
    return Check(name="reachable", status="ok", detail=text.strip()[:60])


def _streams_large(provider, model: str) -> Check:
    """The v0.62.0 bug, as a check.

    A large `max_tokens` is what the implementer sends on every build. If
    the adapter does not switch transports the SDK raises *before sending*
    and no task can ever be built — which shipped to PyPI twice.
    """
    try:
        text = provider.chat(
            model=model,
            system="Answer with exactly one word.",
            messages=[{"role": "user", "content": "Say: streamed"}],
            max_tokens=_BIG_MAX_TOKENS,
        )
    except ProviderError as exc:
        return Check(name="streams_large", status="skipped", detail=str(exc)[:200])
    except Exception as exc:  # noqa: BLE001
        return Check(
            name="streams_large", status="failed",
            detail=f"max_tokens={_BIG_MAX_TOKENS} raised "
                   f"{type(exc).__name__}: {str(exc)[:250]} — this is the "
                   "failure that made `avs create` build nothing at all",
        )
    if not text.strip():
        return Check(
            name="streams_large", status="failed",
            detail="the large-request path returned empty text",
        )
    return Check(name="streams_large", status="ok",
                 detail=f"max_tokens={_BIG_MAX_TOKENS} → {text.strip()[:40]!r}")


def _truncation_visible(provider, model: str) -> Check:
    """A response that hit the cap must be *detectable* as partial.

    `last_response_truncated()` is what makes the build loop refuse a
    half-written file. If an adapter stops recording stop_reason, the guard
    goes quiet and the symptom appears three iterations later as an
    unrelated test error.
    """
    try:
        provider.chat(
            model=model,
            system="Follow the instruction exactly.",
            messages=[{
                "role": "user",
                "content": "Count from 1 to 400, one number per line, no other text.",
            }],
            max_tokens=16,
        )
    except ProviderError as exc:
        return Check(name="truncation_visible", status="skipped", detail=str(exc)[:200])
    except Exception as exc:  # noqa: BLE001
        return Check(
            name="truncation_visible", status="failed",
            detail=f"{type(exc).__name__}: {str(exc)[:250]}",
        )
    if not last_response_truncated():
        from ai_venture_studio.providers.base import last_stop_reason

        return Check(
            name="truncation_visible", status="failed",
            detail=f"a 16-token cap on a 400-line answer reported "
                   f"stop_reason={last_stop_reason()!r} — the truncation "
                   "guard cannot fire, so partial files reach disk",
        )
    return Check(name="truncation_visible", status="ok",
                 detail="a capped response is reported as truncated")


def _usage_metered(provider, model: str) -> Check:
    """`avs cost` and the founder's cost line both read this ledger. An
    adapter that stops metering makes them read zero, which is the one
    number nobody questions."""
    from ai_venture_studio import spend

    before = spend.buffered()
    try:
        provider.chat(
            model=model,
            system="Answer with exactly one word.",
            messages=[{"role": "user", "content": "Say: metered"}],
            max_tokens=_REALISTIC_MIN_TOKENS,
        )
    except ProviderError as exc:
        return Check(name="usage_metered", status="skipped", detail=str(exc)[:200])
    except Exception as exc:  # noqa: BLE001
        return Check(
            name="usage_metered", status="failed",
            detail=f"{type(exc).__name__}: {str(exc)[:250]}",
        )
    if spend.buffered() <= before:
        return Check(
            name="usage_metered", status="failed",
            detail="the call left no entry in the spend ledger — the cost "
                   "gate and the report's cost line would both read zero",
        )
    return Check(name="usage_metered", status="ok",
                 detail=f"{spend.buffered() - before} ledger entr(y/ies) recorded")
