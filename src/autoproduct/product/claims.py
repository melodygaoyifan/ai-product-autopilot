"""Claim ledger (§20.53) — typed, falsifiable product claims.

The outer loop's core problem: a market agent that invents "$2.4B growing
22% CAGR" gets no red test. The claim schema is the missing floor — every
quantitative or comparative assertion in a P-stage artifact is a typed
record with provenance, a reproducible locator, a hashed snapshot, an n,
and a falsifier. Prose that is not a claim is prose; a claim that is not
typed fails `claim_lint`.

`source_type` is the load-bearing field, strictly ordered by strength:
`primary_measured` is the only type that may ground a causal claim;
`model_inference` is permitted, labeled, and capped by ratio per artifact
kind (`.mas/product-policy.yaml`, §20.53.3).
"""

from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field

SOURCE_TYPES = frozenset(
    {
        "primary_measured",  # we ran the measurement — analytics, holdout, probe
        "primary_cited",  # a named first party stated it about itself, with locator
        "third_party_report",  # analyst/survey/press figure — context and sizing only
        "user_reported",  # a real, identified user artifact (§20.53.4)
        "model_inference",  # the model reasoned it out — labeled, ratio-capped
    }
)

CLAIM_KINDS = frozenset(
    {
        "market_size",
        "market_structure",
        "competitor_fact",
        "pricing",
        "demand",
        "channel_performance",
        "user_need",
    }
)

# §20.53.6 — the claim schema refines the hypothesis ledger's evidence
# classes (measured/sourced/assumed, §13.26.5); the mapping is fixed so
# reconciliation (§22.65.3) can walk both directions.
LEDGER_CLASS_BY_SOURCE_TYPE = {
    "primary_measured": "measured",
    "primary_cited": "sourced",
    "third_party_report": "sourced",
    "user_reported": "sourced",
    "model_inference": "assumed",
}

SOURCE_TYPES_BY_LEDGER_CLASS = {
    "measured": ("primary_measured",),
    "sourced": ("primary_cited", "third_party_report", "user_reported"),
    "assumed": ("model_inference",),
}


def ledger_class_for(source_type: str) -> str:
    """Map a claim source_type to its hypothesis-ledger evidence class."""
    try:
        return LEDGER_CLASS_BY_SOURCE_TYPE[source_type]
    except KeyError:
        raise ValueError(f"unknown source_type {source_type!r}") from None


def source_types_for(ledger_class: str) -> tuple[str, ...]:
    """Map a hypothesis-ledger evidence class to its admissible source_types."""
    try:
        return SOURCE_TYPES_BY_LEDGER_CLASS[ledger_class]
    except KeyError:
        raise ValueError(f"unknown ledger class {ledger_class!r}") from None


class EvidenceRef(BaseModel):
    method: str  # reproducible action, not a memory
    locator: str
    retrieved_at: str = ""
    artifact_hash: str = ""  # sha256:… snapshot in .mas/evidence/ (§20.53.5)


class Claim(BaseModel):
    id: str
    text: str
    kind: str = ""
    source_type: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    n: int | None = None
    confidence: float | None = None  # voter-assigned, not writer-asserted
    falsifier: str = ""
    expires: str = ""


# Ratio ceilings for model_inference claims by artifact kind — the defaults
# of §20.53.3. Tunable in .mas/product-policy.yaml; the requirement itself
# is never tunable (risk R-P1: tune the ceilings, never the requirement).
DEFAULT_INFERENCE_CEILINGS = {
    "opportunity": 0.50,
    "market": 0.30,
    "prd": 0.20,
    "launch": 0.20,
}
FALLBACK_INFERENCE_CEILING = 0.30


class ProductPolicy(BaseModel):
    inference_ceilings: dict[str, float] = Field(
        default_factory=lambda: dict(DEFAULT_INFERENCE_CEILINGS)
    )

    def ceiling_for(self, artifact_kind: str) -> float:
        return self.inference_ceilings.get(artifact_kind, FALLBACK_INFERENCE_CEILING)


class ProductPolicyError(RuntimeError):
    """Raised when .mas/product-policy.yaml is malformed. Fails closed."""


def load_product_policy(mas_dir: str | pathlib.Path) -> ProductPolicy:
    """Load .mas/product-policy.yaml; absent file means the shipped defaults."""
    path = pathlib.Path(mas_dir) / "product-policy.yaml"
    if not path.exists():
        return ProductPolicy()
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ProductPolicyError(f"product-policy.yaml is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ProductPolicyError("product-policy.yaml must be a mapping")
    ceilings = dict(DEFAULT_INFERENCE_CEILINGS)
    for kind, value in (raw.get("inference_ceilings") or {}).items():
        if not isinstance(value, (int, float)) or not 0 < value <= 1:
            raise ProductPolicyError(
                f"inference ceiling for {kind!r} must be in (0, 1], got {value!r}"
            )
        ceilings[str(kind)] = float(value)
    return ProductPolicy(inference_ceilings=ceilings)


def load_ledger(path: str | pathlib.Path) -> dict:
    """Read a claims/*.claim.yaml ledger as a plain mapping.

    claim_lint operates on the raw mapping rather than parsed models so a
    malformed ledger produces findings, not a stack trace.
    """
    doc = yaml.safe_load(pathlib.Path(path).read_text())
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: claim ledger must be a YAML mapping")
    return doc
