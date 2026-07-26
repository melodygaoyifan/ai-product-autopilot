"""Gate PL3-exp (§21.61.2) — deterministic entry to any exposure.

Preconditions: pre-registration hash written, MDE reachable, arms
instrumented, FDR plan sound — and no Ethics veto. The Ethics voter's veto
is not a finding to weigh: it stops the experiment on the same footing as
forbidden_autonomous (§21.61.4). Dark patterns, untrue urgency, offer
discrimination across protected characteristics or their proxies, and
experiments on populations who cannot meaningfully consent are vetoes,
full stop.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from autoproduct.experiment.design import ExperimentDesign
from autoproduct.experiment.fdr import fdr_plan_check
from autoproduct.experiment.power import PowerResult


class EthicsVerdict(BaseModel):
    veto: bool
    grounds: str = ""


class GatePL3ExpResult(BaseModel):
    passed: bool
    findings: list[str] = Field(default_factory=list)


def gate_pl3_exp(
    design: ExperimentDesign,
    power_result: PowerResult,
    *,
    arms_instrumented: bool,
    ethics: EthicsVerdict,
) -> GatePL3ExpResult:
    findings: list[str] = []
    if ethics.veto:
        # First and alone on purpose: a veto is not weighed against the rest.
        return GatePL3ExpResult(
            passed=False,
            findings=[f"ETHICS VETO: {ethics.grounds or 'grounds recorded by voter'}"],
        )
    if not design.preregistration_hash:
        findings.append("no pre-registration hash written — nothing is exposed unpinned")
    if power_result.status != "ok":
        findings.append(f"{power_result.status}: {power_result.detail}")
    if not arms_instrumented:
        findings.append("arms lack assignment instrumentation — an unevaluable "
                        "experiment is exposure without measurement")
    for issue in fdr_plan_check(design):
        findings.append(f"fdr_plan:{issue.rule}: {issue.message}")
    return GatePL3ExpResult(passed=not findings, findings=findings)
