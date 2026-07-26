"""P1 Market & Viability — competitor probes and Gate PL1 (§20.55).

Competitor facts are probes, not recollections: `record_probe` does the
bookkeeping for a fetch that already happened (snapshot, hash, evidence
entry) — the fetch itself is an availability-gated runtime wrapper that
reads only what is public and API-permitted, standing-checked against
.mas/signal-sources.yaml. A competitor claim with no probe hash is
model_inference by definition and counts against the 30% market ceiling.

Gate PL1 is human, with a rubric; this module enforces its deterministic
entry conditions and records the outcome. The most common correct outcome
is `test_first` — measure before you build.
"""

from __future__ import annotations

import datetime as dt
import pathlib

from pydantic import BaseModel, Field, field_validator

from autoproduct.product.claim_lint import lint_ledger
from autoproduct.product.claims import ProductPolicy
from autoproduct.product.evidence import store_snapshot
from autoproduct.product.injection import InjectionFinding, injection_scan
from autoproduct.product.sizing import SizingResult
from autoproduct.product.sources import (
    SignalSource,
    SignalSourceError,
    source_standing_check,
)

GATE_PL1_RUBRIC = (
    "Is the size range built bottom-up from factors I can each check?",
    "What is the strongest disconfirming finding, and is the answer evidence "
    "or narrative?",
    "Which factors are model_inference, and does the decision survive their "
    "sensitivity range?",
    "Does any regulatory finding change the shape of what we'd build?",
    "What is the cheapest test that would move me, and why aren't we running "
    "it first?",
)


def record_probe(
    content: bytes,
    *,
    locator: str,
    retrieved_at: str,
    sources: list[SignalSource],
    mas_dir: str | pathlib.Path,
    method: str = "competitor_probe",
) -> dict:
    """Snapshot a probe result and return the ledger-ready evidence entry.
    Refuses locators with no declared standing — probing where nobody
    granted access is not evidence gathering (§20.55.3)."""
    probe_doc = {"claims": [{"id": "_probe", "evidence": [{"locator": locator}]}]}
    if source_standing_check(probe_doc, sources):
        raise SignalSourceError(
            f"probe target {locator!r} matches no declared source — no standing, "
            "no probe (§20.55.3 hard boundary)"
        )
    snapshot = store_snapshot(content, mas_dir)
    return {
        "method": method,
        "locator": locator,
        "retrieved_at": retrieved_at,
        "artifact_hash": snapshot.artifact_hash,
    }


class GatePL1Entry(BaseModel):
    passed: bool
    findings: list[str]
    injection_findings: list[InjectionFinding] = Field(default_factory=list)


class GatePL1Decision(BaseModel):
    outcome: str  # pursue | test_first | park | reject
    decider: str  # a named human — forbidden_autonomous, always
    scope_tier: str = ""  # required for pursue
    named_test: str = ""  # required for test_first
    park_reason: str = ""  # required for park; routes to the kill registry

    @field_validator("decider")
    @classmethod
    def _named_human(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Gate PL1 is human, always (§21.57.2)")
        return value

    @field_validator("outcome")
    @classmethod
    def _legal(cls, value: str) -> str:
        if value not in {"pursue", "test_first", "park", "reject"}:
            raise ValueError("outcome is pursue | test_first | park | reject")
        return value

    def validate_completeness(self) -> None:
        if self.outcome == "pursue" and self.scope_tier not in {
            "thin",
            "standard",
            "deep",
        }:
            raise ValueError("pursue requires a scope_tier (thin|standard|deep)")
        if self.outcome == "test_first" and not self.named_test.strip():
            raise ValueError("test_first requires the named cheapest test")
        if self.outcome == "park" and not self.park_reason.strip():
            raise ValueError("park requires a reason — it becomes registry history")


def gate_pl1_entry(
    market_ledger: dict,
    sizing: SizingResult,
    *,
    mas_dir: str | pathlib.Path,
    disconfirmation_answered: bool,
    regulatory_triaged: bool,
    today: dt.date | None = None,
    policy: ProductPolicy | None = None,
) -> GatePL1Entry:
    """The deterministic preconditions of §20.55.5. The rubric and the
    decision stay human; contaminated claims cannot ground entry."""
    findings: list[str] = []
    for issue in lint_ledger(market_ledger, "market", today=today, policy=policy):
        findings.append(f"claim_lint:{issue.rule}: {issue.message}")
    if sizing.status != "ok" or sizing.result_range is None:
        findings.append("sizing: no bottom-up range with sensitivities")
    injection = injection_scan(market_ledger, mas_dir)
    for finding in injection:
        if finding.rule in ("contaminated", "snapshot_drift"):
            findings.append(f"injection:{finding.rule}: claim {finding.claim_id}")
    if not disconfirmation_answered:
        findings.append(
            "disconfirmation findings not answered — answered ≠ dismissed"
        )
    if not regulatory_triaged:
        findings.append("regulatory findings not triaged")
    return GatePL1Entry(
        passed=not findings, findings=findings, injection_findings=injection
    )
