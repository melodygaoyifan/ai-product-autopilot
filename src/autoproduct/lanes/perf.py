"""The performance lane (doc 26) — "high traffic" as a checkable claim.

Perf ACs are lintable (UNDER <load-shape> THE SYSTEM SHALL <metric> <op>
<value> [AT pXX] [FOR <dur>]); vague perf words die like "fast" did. A
load-test run is typed VALID or INVALID_RUN from five deterministically
checkable preconditions — an INVALID_RUN is not a worse number, it is NOT
A NUMBER (ADR-U30). capacity.yaml is checked arithmetically at Gate 5.
The lane ships PROVISIONAL until its seeded perf-defect manifest is
calibrated (§19 rule); k6/Locust execution is an availability-gated
wrapper — this module is the deterministic contract around it.
"""

from __future__ import annotations

import datetime as dt
import re

from pydantic import BaseModel, Field

PERF_AC = re.compile(
    r"^UNDER\s+(?P<shape>.+?)\s+THE SYSTEM SHALL\s+(?P<metric>[\w.]+)\s*"
    r"(?P<op><=|<|>=|>)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|s|%|rps)?"
    r"(?:\s+AT\s+p(?P<pct>50|95|99))?(?:\s+FOR\s+(?P<dur>\d+[smh]))?\s*$",
    re.I,
)
_ARRIVAL = re.compile(r"\b(open|closed)\b", re.I)
VAGUE_PERF = re.compile(
    r"\b(high traffic|scales? well|low latency|supports? many users|"
    r"performant|blazing|snappy|handles? load)\b",
    re.I,
)

# The seeded perf-defect manifest (§77.2) — the lane's calibration targets.
SEEDED_PERF_DEFECTS = (
    "n_plus_one_query",
    "missing_index_on_filtered_column",
    "unbounded_connection_pool",
    "sync_call_in_async_handler",
    "quadratic_serializer_on_list_endpoint",
)
LANE_STATUS = "PROVISIONAL"  # until the seeded manifest is calibrated


class PerfLintIssue(BaseModel):
    index: int
    criterion: str
    problem: str


def lint_perf_criteria(criteria: list[str]) -> list[PerfLintIssue]:
    issues = []
    for i, criterion in enumerate(criteria):
        text = criterion.strip()
        vague = VAGUE_PERF.search(text)
        if vague:
            issues.append(PerfLintIssue(
                index=i, criterion=criterion,
                problem=f"vague perf term {vague.group(0)!r} — use the UNDER/"
                        "SHALL grammar with a number (§77.1)"))
            continue
        match = PERF_AC.match(text)
        if not match:
            issues.append(PerfLintIssue(
                index=i, criterion=criterion,
                problem="does not match: UNDER <load-shape> THE SYSTEM SHALL "
                        "<metric> <op> <value> [AT pXX] [FOR <dur>]"))
            continue
        if not _ARRIVAL.search(match.group("shape")) and not re.search(
            r"\brps\b|\bconcurrent\b", match.group("shape"), re.I
        ):
            issues.append(PerfLintIssue(
                index=i, criterion=criterion,
                problem="load-shape must name an arrival model (open/rps-driven "
                        "or closed/concurrent-VU) — conflating them is how a "
                        "test passes while production burns"))
    return issues


class PerfRunTelemetry(BaseModel):
    generator_cpu_max: float  # 0..1
    dropped_iterations: int = 0
    blocked_spike: bool = False
    entry_point: str  # e.g. "cdn" | "origin"
    slo_entry_point: str
    arrival_model: str  # open | closed
    ac_arrival_model: str
    environment: str
    environment_parity: str  # low | prod_mirror | prod
    slot: str  # perf_smoke | perf_regression | perf_soak | perf_spike
    percentiles: dict[str, float] = Field(default_factory=dict)  # p50/p95/p99


class PerfRunVerdict(BaseModel):
    status: str  # VALID | INVALID_RUN
    failures: list[str]


def type_perf_run(t: PerfRunTelemetry) -> PerfRunVerdict:
    """ADR-U30: only VALID runs may update baselines, satisfy ACs, or
    ground claims. Failures are named, never warned-and-recorded."""
    failures = []
    if t.generator_cpu_max >= 0.80 or t.dropped_iterations or t.blocked_spike:
        failures.append("generator_saturated: exhausted generators flatter the "
                        "system under test (precondition 1)")
    if t.entry_point != t.slo_entry_point:
        failures.append(f"measurement_path_mismatch: measured via "
                        f"{t.entry_point!r}, SLO includes {t.slo_entry_point!r}")
    if t.arrival_model != t.ac_arrival_model:
        failures.append("arrival_model_mismatch: run model differs from the "
                        "AC's declared load shape")
    if t.slot in ("perf_regression", "perf_soak") and t.environment_parity != "prod_mirror":
        failures.append(f"environment_parity: {t.slot} requires prod_mirror, "
                        f"got {t.environment_parity!r} — localhost smoke-tests "
                        "scripts, never satisfies ACs")
    if not {"p50", "p95", "p99"} <= set(t.percentiles):
        failures.append("percentile_honesty: p50/p95/p99 required; mean-only "
                        "reporting is how p99 pathologies hide")
    return PerfRunVerdict(status="INVALID_RUN" if failures else "VALID",
                          failures=failures)


class CapacityIssue(BaseModel):
    endpoint: str
    rule: str
    message: str


def capacity_check(
    entries: list[dict],
    *,
    valid_runs: set[str],
    last_perf_relevant_merge: dt.date,
) -> list[CapacityIssue]:
    """Gate 5's deterministic capacity review (§77.4):
    expected × peak × 2 <= measured saturation, from a VALID in-repo run."""
    issues = []
    for entry in entries:
        endpoint = str(entry.get("endpoint", "?"))
        traffic = entry.get("traffic_model") or {}
        measured = entry.get("measured") or {}
        run = str(measured.get("run", ""))
        if run not in valid_runs:
            issues.append(CapacityIssue(
                endpoint=endpoint, rule="no_valid_run",
                message=f"measured.run {run!r} does not resolve to a VALID run "
                        "in-repo — an INVALID_RUN is not a number (ADR-U30)"))
            continue
        try:
            at = dt.date.fromisoformat(str(measured.get("at", "")))
        except ValueError:
            issues.append(CapacityIssue(endpoint=endpoint, rule="stale",
                                        message="measured.at missing/unparseable"))
            continue
        if at < last_perf_relevant_merge:
            issues.append(CapacityIssue(
                endpoint=endpoint, rule="stale",
                message=f"measured {at} predates the last perf-relevant merge "
                        f"({last_perf_relevant_merge}) — re-measure"))
        need = float(traffic.get("expected_rps", 0)) * float(
            traffic.get("peak_multiplier", 1)) * 2
        have = float(measured.get("saturation_rps", 0))
        if need > have:
            issues.append(CapacityIssue(
                endpoint=endpoint, rule="insufficient_headroom",
                message=f"peak×2 = {need:g} rps exceeds measured saturation "
                        f"{have:g} rps (headroom policy §77.4)"))
    return issues
