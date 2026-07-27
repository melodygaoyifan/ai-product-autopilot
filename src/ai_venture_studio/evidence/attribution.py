"""attribution_typer (§22.63.2, ADR-U25) — typing at the tool boundary.

Attribution does not work the way dashboards imply: last-touch over-credits
demand capture, a third or more of the journey is invisible to trackers,
and the methods practitioners trust are holdouts, self-reported answers,
and MMM — with multi-touch demoted to a hint. The framework's response is
not "attribution is hard"; it is a typing rule, applied where data enters
rather than where prose is written:

- only a holdout may ground a causal claim;
- MMM / multi-touch / last-touch / correlation are model_inference;
- platform-reported figures are third_party_report (the seller grading
  its own work);
- self-reported answers are user_reported (real answers, biased recall).

"The launch post drove 40% of signups" is rejected unless it came from a
holdout. "40% of signups arrived with the launch-post UTM, and 31% of
respondents named the post" is accepted — two typed observations, no
causal verb.
"""

from __future__ import annotations

from pydantic import BaseModel

from ai_venture_studio.product.claim_lint import has_causal_language

# method → (source_type, may_ground_causal_claim). §22.63.2 verbatim.
ATTRIBUTION_RULES: dict[str, tuple[str, bool]] = {
    "holdout_experiment": ("primary_measured", True),  # the only causal ones
    "geo_holdout": ("primary_measured", True),
    "self_reported": ("user_reported", False),  # real answers, biased recall
    "mmm": ("model_inference", False),  # a model, however good
    "multi_touch": ("model_inference", False),
    "last_touch": ("model_inference", False),
    "platform_reported": ("third_party_report", False),  # seller grading itself
    "correlation": ("model_inference", False),
}


class AttributionMethodError(RuntimeError):
    """An undeclared attribution method. Typing is mandatory at the
    boundary — there is no 'best available attribution' default (ADR-U25)."""


class TypedObservation(BaseModel):
    method: str
    source_type: str
    may_ground_causal: bool


class AttributionFinding(BaseModel):
    rule: str
    message: str


def type_observation(method: str) -> TypedObservation:
    try:
        source_type, causal = ATTRIBUTION_RULES[method]
    except KeyError:
        raise AttributionMethodError(
            f"attribution method {method!r} is not in the typing table — declare "
            f"one of {sorted(ATTRIBUTION_RULES)}; unlabeled attribution does not "
            "enter the ledger"
        ) from None
    return TypedObservation(
        method=method, source_type=source_type, may_ground_causal=causal
    )


def attribute_claim(text: str, method: str) -> dict | list[AttributionFinding]:
    """Build a ledger-ready claim from an attribution observation, or reject
    it. A causal sentence with a non-causal method is refused HERE, at the
    boundary — before claim_lint would refuse it again at the gate
    (invariant 14.18, both layers on purpose)."""
    typed = type_observation(method)
    if has_causal_language(text) and not typed.may_ground_causal:
        return [
            AttributionFinding(
                rule="causal_without_experiment",
                message=f"causal language over {method!r} ({typed.source_type}) — "
                "only a holdout grounds a causal claim; restate as typed "
                "observations or run the holdout (§22.63.3)",
            )
        ]
    return {
        "text": text,
        "kind": "channel_performance",
        "source_type": typed.source_type,
        "attribution_method": method,
    }
