"""Continuous-operation policy (doc 16 §38-39) — WIP, the shared-file
registry, and the shed rule, as loadable schemas with deterministic checks.

`.mas/operations-policy.yaml` carries per-stage WIP limits, the human
queue limit, and latency SLOs; `.mas/hot-files.yaml` is the global
shared-file registry consulted by lanes and Sweep. The shed rule (§39.3):
when the human queue exceeds its limit, intake stops pulling — protecting
the queue by throttling input, never by lowering gates.
"""

from __future__ import annotations

import fnmatch
import pathlib

import yaml
from pydantic import BaseModel, Field

OPERATIONS_FILE = "operations-policy.yaml"
HOT_FILES_FILE = "hot-files.yaml"

DEFAULT_WIP = {
    "discovery": 2, "planning": 2, "spec": 2, "coding_features": 2,
    "coding_lanes_total": 4, "review_queue": 6,
}


class OperationsPolicy(BaseModel):
    wip_limits: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_WIP))
    human_queue_limit: int = 8
    latency_slo_hours: float = 24.0
    ci_concurrency_max: int = 4  # F-16.1: ships on by default


class OperationsError(RuntimeError):
    pass


def load_operations_policy(mas_dir: str | pathlib.Path) -> OperationsPolicy:
    path = pathlib.Path(mas_dir) / OPERATIONS_FILE
    if not path.exists():
        return OperationsPolicy()
    raw = yaml.safe_load(path.read_text()) or {}
    limits = dict(DEFAULT_WIP)
    for stage, value in (raw.get("wip_limits") or {}).items():
        if not isinstance(value, int) or value < 1:
            raise OperationsError(f"wip_limits.{stage} must be a positive int")
        limits[str(stage)] = value
    return OperationsPolicy(
        wip_limits=limits,
        human_queue_limit=int(raw.get("human_queue_limit", 8)),
        latency_slo_hours=float(raw.get("latency_slo_hours", 24.0)),
        ci_concurrency_max=int(raw.get("ci_concurrency_max", 4)),
    )


class WipCheck(BaseModel):
    stage: str
    in_flight: int
    limit: int
    admit: bool
    reason: str


def wip_check(policy: OperationsPolicy, stage: str, in_flight: int) -> WipCheck:
    limit = policy.wip_limits.get(stage, 2)
    admit = in_flight < limit
    return WipCheck(stage=stage, in_flight=in_flight, limit=limit, admit=admit,
                    reason="within WIP" if admit else
                    f"WIP limit {limit} reached — finish before starting (§38.2)")


def shed_check(policy: OperationsPolicy, human_queue_depth: int) -> bool:
    """True = KEEP PULLING intake; False = shed (stop pulling) — the queue
    is protected by throttling input, never by lowering gates (§39.3)."""
    return human_queue_depth <= policy.human_queue_limit


class HotFileEntry(BaseModel):
    pattern: str  # glob over repo-relative paths
    owner_lane: str = ""  # active feature lane that owns it, if any
    lanes_max: int = 1  # how many lanes may touch it concurrently


class LaneConflict(BaseModel):
    path: str
    pattern: str
    owner_lane: str
    message: str


def load_hot_files(mas_dir: str | pathlib.Path) -> list[HotFileEntry]:
    path = pathlib.Path(mas_dir) / HOT_FILES_FILE
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text()) or {}
    return [HotFileEntry(**e) for e in raw.get("hot_files") or []]


def lane_check(
    files_touched: list[str], registry: list[HotFileEntry], *, lane: str
) -> list[LaneConflict]:
    """The cross-feature rule (§38.2 rule 1) — Sweep and feature lanes
    consult this and skip-and-report rather than collide (F-29.3)."""
    conflicts = []
    for path in files_touched:
        for entry in registry:
            if fnmatch.fnmatch(path, entry.pattern):
                if entry.owner_lane and entry.owner_lane != lane:
                    conflicts.append(LaneConflict(
                        path=path, pattern=entry.pattern,
                        owner_lane=entry.owner_lane,
                        message=f"{path} is owned by active lane "
                                f"{entry.owner_lane!r} — skip and report"))
    return conflicts
