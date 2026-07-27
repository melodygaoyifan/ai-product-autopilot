"""Experiment MAS deterministic layer (§21.61, ADR-U24, weeks P12-P14).

Launch as a set of tests: pre-registered and hash-pinned before exposure,
one primary metric, BH-controlled screening then fresh-sample validation,
sequential-safe monitoring or none, guardrail vetoes, underpowered designs
not run, inconclusive results entering nothing. The Validity /
Metric-Integrity / Ethics / Sample-Feasibility voter charters live in
skills/marketing/.
"""

from ai_venture_studio.experiment.design import (
    ExperimentDesign,
    Monitoring,
    PowerSpec,
    PreregistrationError,
    StageOne,
    StageTwo,
    canonical_design_text,
    load_design,
    lock_preregistration,
    verify_at_analysis,
)
from ai_venture_studio.experiment.fdr import (
    BHResult,
    FdrPlanIssue,
    benjamini_hochberg,
    fdr_plan_check,
)
from ai_venture_studio.experiment.gate import EthicsVerdict, GatePL3ExpResult, gate_pl3_exp
from ai_venture_studio.experiment.power import PowerResult, power_calc
from ai_venture_studio.experiment.sequential import (
    IllegalStopError,
    PeekVerdict,
    declare_stop,
    obrien_fleming_boundaries,
    peek,
)
from ai_venture_studio.experiment.two_stage import (
    ArmReading,
    CompoundingBoundaryError,
    DecisionRecord,
    GuardrailReading,
    admit_to_compounding,
    run_two_stage,
    screen_stage1,
    two_proportion_p,
)

__all__ = [
    "ArmReading",
    "BHResult",
    "CompoundingBoundaryError",
    "DecisionRecord",
    "EthicsVerdict",
    "ExperimentDesign",
    "FdrPlanIssue",
    "GatePL3ExpResult",
    "GuardrailReading",
    "IllegalStopError",
    "Monitoring",
    "PeekVerdict",
    "PowerResult",
    "PowerSpec",
    "PreregistrationError",
    "StageOne",
    "StageTwo",
    "admit_to_compounding",
    "benjamini_hochberg",
    "canonical_design_text",
    "declare_stop",
    "fdr_plan_check",
    "gate_pl3_exp",
    "load_design",
    "lock_preregistration",
    "obrien_fleming_boundaries",
    "peek",
    "power_calc",
    "run_two_stage",
    "screen_stage1",
    "two_proportion_p",
    "verify_at_analysis",
]
