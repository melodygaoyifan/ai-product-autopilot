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

from autoproduct.adoption.evidence import build_evidence_bundle, write_evidence_bundle
from autoproduct.adoption.gate_r import (
    ChangePackage,
    GateREntry,
    gate_r_entry,
    load_preflight_checklist,
    record_rejection,
)
from autoproduct.adoption.readiness import readiness_report
from autoproduct.adoption.substrate import (
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

__all__ = [
    "ChangePackage",
    "GateREntry",
    "Rung",
    "StageActivation",
    "StageInactiveError",
    "StageStatus",
    "SubstrateProfile",
    "build_evidence_bundle",
    "check_stage",
    "gate_r_entry",
    "load_preflight_checklist",
    "load_substrate_profile",
    "readiness_report",
    "record_rejection",
    "rung_banner",
    "stage_activation",
    "write_evidence_bundle",
]
