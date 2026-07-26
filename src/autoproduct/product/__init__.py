"""Product-loop substrate (docs 20-23, weeks P1-P2) — the evidence floor.

The outer loop has no compiler, no test suite, no type checker; the typed
claim ledger and the checks in this package are built to be what ears_lint
is upstream. Everything else in the product loop (P0-P5 stages, gates,
voters) stands on this substrate and ships in later milestones.
"""

from autoproduct.product.claim_lint import ClaimIssue, lint_ledger
from autoproduct.product.claims import (
    Claim,
    ProductPolicy,
    ProductPolicyError,
    ledger_class_for,
    load_ledger,
    load_product_policy,
    source_types_for,
)
from autoproduct.product.evidence import (
    Snapshot,
    resolve_snapshot,
    snapshot_differs,
    store_snapshot,
    verify_snapshot,
)
from autoproduct.product.persona_scan import PersonaFinding, synthetic_persona_scan
from autoproduct.product.sources import (
    SignalSource,
    SignalSourceError,
    load_signal_sources,
    source_standing_check,
)
from autoproduct.product.taint import TaintPolicyError, load_taint_classes

__all__ = [
    "Claim",
    "ClaimIssue",
    "PersonaFinding",
    "ProductPolicy",
    "ProductPolicyError",
    "SignalSource",
    "SignalSourceError",
    "Snapshot",
    "TaintPolicyError",
    "ledger_class_for",
    "lint_ledger",
    "load_ledger",
    "load_product_policy",
    "load_signal_sources",
    "load_taint_classes",
    "resolve_snapshot",
    "snapshot_differs",
    "source_standing_check",
    "source_types_for",
    "store_snapshot",
    "synthetic_persona_scan",
    "verify_snapshot",
]
