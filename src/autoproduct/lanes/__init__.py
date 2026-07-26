"""Complex-systems lanes and deltas (docs 26-28): performance, realtime,
streaming, architecture evolution, delivery hardening. All deterministic;
external engines (k6, netem, registries) are availability-gated wrappers
around these contracts. The perf lane is PROVISIONAL until its seeded
manifest is calibrated (§19 rule)."""

from autoproduct.lanes.arch import (
    ApiSurfaceIssue, ArchViolation, CheckpointResult, DepsGraphError,
    api_surface_check, arch_contract_check, checkpoint_check, graph_fingerprint,
    load_deps,
)
from autoproduct.lanes.delivery import (
    EnvironmentsError, FlagIssue, RehearsalRecord, check_environments,
    expand_contract_violation, flag_lint, migration_rehearsal,
    perf_run_environment_ok,
)
from autoproduct.lanes.perf import (
    LANE_STATUS, SEEDED_PERF_DEFECTS, CapacityIssue, PerfLintIssue,
    PerfRunTelemetry, PerfRunVerdict, capacity_check, lint_perf_criteria,
    type_perf_run,
)
from autoproduct.lanes.realtime import (
    NET_MODELS, NetModelIssue, ReplayVerdict, SimScanFinding, check_net_model,
    cross_build_replay, desync_probe, det_sim_scan, replay_identity,
    tick_budget_ok,
)
from autoproduct.lanes.streaming import (
    COMPAT_MODES, UPGRADE_ORDER, BackpressureFinding, DeliveryClaim,
    StreamContractError, StreamIssue, backpressure_scan, check_compatibility,
    load_stream_contracts, stream_contract_check, type_delivery_claim,
)

__all__ = [n for n in dir() if not n.startswith("_")]
