"""Traditional-industry adoption track (docs 18-19, ADR-U15..U18).

- substrate: the S0-S4 adoption ladder (§18.47.1) — stage activation from a
  declared infrastructure profile; below-floor stages are inactive, never
  silently degraded.
- readiness: the generated modernization roadmap (§19 G1 Day 4).
- gate_r: regulated change control as an external gate (§18.47.3) — CAB
  preflight checklist + rejection-to-fixture loop; submission human-only.
- evidence: the per-change evidence bundle assembled from the YAML mirror
  (§19 G2 Day 9-10; unsigned v0 until the attestation ledger lands).
"""

from ai_venture_studio.adoption.attestation import (
    LedgerVerification,
    append_attestation,
    attest_review,
    review_attested,
    verify_ledger,
)
from ai_venture_studio.adoption.banners import adoption_banners
from ai_venture_studio.adoption.calibrate import (
    CalibrationReport,
    calibration_report,
    write_calibration_report,
)
from ai_venture_studio.adoption.data_gates import (
    ContractViolation,
    EvalGateResult,
    IdempotencyResult,
    contract_check,
    eval_gate,
    idempotency_check,
    load_contract,
    pin_baseline,
)
from ai_venture_studio.adoption.data_tools import data_check_spec, run_data_checks
from ai_venture_studio.adoption.dwell import DwellReport, gate_dwell_report
from ai_venture_studio.adoption.evidence import build_evidence_bundle, write_evidence_bundle
from ai_venture_studio.adoption.gate_r import (
    ChangePackage,
    GateREntry,
    gate_r_entry,
    load_preflight_checklist,
    prepare_change_package,
    record_rejection,
    save_change_package,
)
from ai_venture_studio.adoption.readiness import readiness_report
from ai_venture_studio.adoption.substrate import (
    Rung,
    StageActivation,
    StageInactiveError,
    StageStatus,
    SubstrateProfile,
    check_stage,
    load_substrate_profile,
    rung_banner,
    stage_activation,
)
from ai_venture_studio.adoption.toolchains import (
    BenchmarkResult,
    ToolchainRecord,
    ToolchainReport,
    benchmark_toolchain,
    load_seeded_manifest,
    register_toolchain,
    run_toolchain,
    toolchain_banner,
    toolchain_spec,
)

__all__ = [
    "BenchmarkResult",
    "CalibrationReport",
    "ChangePackage",
    "ContractViolation",
    "DwellReport",
    "EvalGateResult",
    "GateREntry",
    "IdempotencyResult",
    "Rung",
    "StageActivation",
    "StageInactiveError",
    "StageStatus",
    "SubstrateProfile",
    "ToolchainRecord",
    "ToolchainReport",
    "LedgerVerification",
    "adoption_banners",
    "append_attestation",
    "attest_review",
    "benchmark_toolchain",
    "build_evidence_bundle",
    "calibration_report",
    "check_stage",
    "contract_check",
    "data_check_spec",
    "eval_gate",
    "gate_dwell_report",
    "gate_r_entry",
    "idempotency_check",
    "load_contract",
    "load_preflight_checklist",
    "load_seeded_manifest",
    "load_substrate_profile",
    "pin_baseline",
    "prepare_change_package",
    "readiness_report",
    "record_rejection",
    "register_toolchain",
    "review_attested",
    "run_data_checks",
    "run_toolchain",
    "rung_banner",
    "save_change_package",
    "stage_activation",
    "toolchain_banner",
    "toolchain_spec",
    "verify_ledger",
    "write_calibration_report",
    "write_evidence_bundle",
]
