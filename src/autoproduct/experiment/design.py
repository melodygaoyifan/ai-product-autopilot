"""Experiment design schema + preregistration lock (§21.61.2-.3, ADR-U24).

Measured FDR in A/B testing is 18-25% at α=0.05 with ~70% true nulls, and
~57% of experimenters p-hack by stopping at significance. The rules that
do the work here:

- ONE primary metric — the single rule that removes the largest source of
  agent-driven multiplicity; secondaries are reported, never decisive.
- Pre-registration is hash-pinned BEFORE exposure; `verify_at_analysis`
  compares the analysis-time design to the pin — a mismatch is a gate
  failure, not a warning. This makes p-hacking structurally impossible
  rather than discouraged.
- The stopping rule is the plan's or the boundary's. No other stop is legal.
"""

from __future__ import annotations

import hashlib
import re

import yaml
from pydantic import BaseModel, Field, field_validator


class StageOne(BaseModel):
    arms: int
    allocation: str = "equal"
    correction: str = "benjamini_hochberg"
    q: float = 0.10


class StageTwo(BaseModel):
    arms: int = 2
    allocation: str = "equal"
    fresh_sample: bool


class PowerSpec(BaseModel):
    baseline: float
    mde_relative: float
    alpha: float = 0.05
    power: float = 0.80
    n_per_arm: int = 0  # filled by power_calc
    expected_days: int = 0


class Monitoring(BaseModel):
    method: str = "sequential"
    spending: str = "obrien_fleming"
    peeks: int = 4  # planned looks, horizon included


class ExperimentDesign(BaseModel):
    id: str
    hypothesis: str
    primary_metric: str  # exactly one — the field is scalar on purpose
    guardrail_metrics: list[str] = Field(default_factory=list)
    secondary_metrics: list[str] = Field(default_factory=list)  # never decisive
    design_stage1: StageOne
    design_stage2: StageTwo
    power: PowerSpec
    monitoring: Monitoring
    stopping_rule: str
    decision_rule: str
    preregistered_at: str = ""
    preregistration_hash: str = ""

    @field_validator("primary_metric")
    @classmethod
    def _exactly_one(cls, value: str) -> str:
        if not value.strip() or "," in value or " and " in value:
            raise ValueError(
                "exactly one primary metric — everything else is a guardrail "
                "or a secondary (§21.61.3)"
            )
        return value

    @field_validator("stopping_rule", "decision_rule")
    @classmethod
    def _stated(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("stopping and decision rules are stated up front, or "
                             "the experiment is a peek generator")
        return value


class PreregistrationError(RuntimeError):
    """The analysis-time design does not match the pre-exposure pin."""


_HASH_LINE = re.compile(r"^\s*preregistration_hash\s*:.*$", re.M)


def canonical_design_text(design_yaml_text: str) -> str:
    """The hash covers everything except the hash line itself."""
    return _HASH_LINE.sub("", design_yaml_text).strip()


def lock_preregistration(design_yaml_text: str) -> str:
    """Pin the design before any exposure. Returns the hash to record both
    in the file and in the experiment registry."""
    canonical = canonical_design_text(design_yaml_text)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def verify_at_analysis(design_yaml_text: str, pinned_hash: str) -> None:
    """Called before any result is read. A post-hoc edit — a new secondary,
    a moved horizon, a reworded hypothesis — fails here by construction."""
    actual = lock_preregistration(design_yaml_text)
    if actual != pinned_hash:
        raise PreregistrationError(
            f"design hash {actual[:16]}… does not match the pre-registration "
            f"pin {pinned_hash[:16]}… — the design was edited after exposure; "
            "the analysis is void (§21.61.3, invariant 14.17)"
        )


def load_design(design_yaml_text: str) -> ExperimentDesign:
    raw = yaml.safe_load(design_yaml_text)
    if not isinstance(raw, dict) or not isinstance(raw.get("experiment"), dict):
        raise ValueError("design must contain an 'experiment' mapping")
    spec = dict(raw["experiment"])
    design = spec.pop("design", {}) or {}
    spec["design_stage1"] = design.get("stage1", {})
    spec["design_stage2"] = design.get("stage2", {})
    return ExperimentDesign(**spec)
