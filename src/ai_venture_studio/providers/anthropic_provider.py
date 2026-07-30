from __future__ import annotations

import os

from ai_venture_studio.providers.base import (
    Provider,
    ProviderError,
    record_stop_reason,
    register,
)


def _make_client():
    """Direct API by default; AVS_ANTHROPIC_MODE=bedrock|vertex routes the
    same Messages API through AWS Bedrock or GCP Vertex — the two doors most
    enterprises actually have. Every mode errors loudly on missing
    credentials rather than running half-armed; nothing here is a silent
    fallback to a different provider."""
    import anthropic

    mode = os.environ.get("AVS_ANTHROPIC_MODE", "direct").strip().lower() or "direct"
    if mode == "bedrock":
        try:
            return anthropic.AnthropicBedrock()
        except Exception as exc:
            raise ProviderError(
                "AVS_ANTHROPIC_MODE=bedrock but the Bedrock client could not "
                f"start ({exc}). Install `anthropic[bedrock]` and provide AWS "
                "credentials (env/instance profile) with bedrock:InvokeModel; "
                "profiles must name Bedrock model IDs (anthropic.claude-* / "
                "region-prefixed variants)."
            ) from exc
    if mode == "vertex":
        if not (
            os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
            and os.environ.get("CLOUD_ML_REGION")
        ):
            raise ProviderError(
                "AVS_ANTHROPIC_MODE=vertex requires ANTHROPIC_VERTEX_PROJECT_ID "
                "and CLOUD_ML_REGION"
            )
        try:
            return anthropic.AnthropicVertex()
        except Exception as exc:
            raise ProviderError(
                "AVS_ANTHROPIC_MODE=vertex but the Vertex client could not "
                f"start ({exc}). Install `anthropic[vertex]` and authenticate "
                "with Application Default Credentials."
            ) from exc
    if mode != "direct":
        raise ProviderError(
            f"unknown AVS_ANTHROPIC_MODE {mode!r}; expected direct|bedrock|vertex"
        )
    # ANTHROPIC_AUTH_TOKEN covers enterprise LLM gateways (bearer auth), and
    # the SDK honors ANTHROPIC_BASE_URL natively, so a proxy needs no code.
    if not (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    ):
        raise ProviderError(
            "ANTHROPIC_API_KEY is not set (a gateway bearer token via "
            "ANTHROPIC_AUTH_TOKEN also works; set AVS_ANTHROPIC_MODE="
            "bedrock|vertex to route through AWS or GCP instead)"
        )
    return anthropic.Anthropic()


@register
class AnthropicProvider(Provider):
    name = "anthropic"

    def chat(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
    ) -> str:
        import time

        import anthropic

        client = _make_client()
        # Transient-error resilience at the ADAPTER layer: overload/rate
        # limits retry with backoff here, so every direct .complete() call
        # site (writers, critics, implementer) inherits it — a 529 killed
        # an entire 2-hour bench run before this existed.
        response = None
        for attempt in range(4):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,
                )
                break
            except (
                anthropic.APIStatusError,
                anthropic.APIConnectionError,
            ) as exc:
                status = getattr(exc, "status_code", None)
                transient = status in (429, 500, 502, 503, 529) or isinstance(
                    exc, anthropic.APIConnectionError
                )
                if not transient or attempt == 3:
                    raise
                time.sleep(2 ** (attempt + 1))
        # Record why the model stopped on EVERY response, not only the empty
        # ones. `stop_reason == "max_tokens"` means the text below is a partial
        # answer, and a partial answer that parses is worse than one that
        # doesn't — see providers/base.py.
        record_stop_reason(getattr(response, "stop_reason", None))

        # Meter here, where usage exists. The chat() contract still returns
        # str — threading a usage object through the writers, critics,
        # implementer and verifier would touch every call site for no gain,
        # and this adapter already owns retries and empty-response
        # diagnostics. Recording never raises; the ledger is written later by
        # whoever knows the workspace (spend.flush).
        usage = getattr(response, "usage", None)
        if usage is not None:
            from ai_venture_studio import spend

            spend.record(
                model,
                getattr(usage, "input_tokens", None),
                getattr(usage, "output_tokens", None),
            )

        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        if not text.strip():
            # Diagnostics for the empty-response mystery (context voter,
            # PR #9): keep the API's own explanation for the failure note.
            global LAST_EMPTY_META
            LAST_EMPTY_META = {
                "model": model,
                "stop_reason": getattr(response, "stop_reason", None),
                "output_tokens": getattr(
                    getattr(response, "usage", None), "output_tokens", None
                ),
                "content_blocks": [getattr(b, "type", "?") for b in response.content],
            }
        return text


LAST_EMPTY_META: dict | None = None
