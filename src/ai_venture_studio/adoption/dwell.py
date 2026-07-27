"""Approval-dwell-time metric — the F-18.3 rubber-stamp detector (§18.50.3).

Compliance theater is an attestation ledger with approvals nobody read.
Its fingerprint is measurable: dwell time (Gate-3 pause → human decision)
collapsing toward zero WITH a zero override rate. Either alone is fine —
fast acks on trivial escalations happen, and high override rates mean the
gate is working. Both together, across enough samples, means the gate is
being clicked through, and the shed rule (§16.39.3) applies.

Dwell is measured from the mirror: the `escalate` step's written_at (the
pause) to the `final` step's written_at (post-resume), per review under
`.mas/reviews/`. Reviews that never escalated contribute nothing.
"""

from __future__ import annotations

import datetime
import statistics
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

RUBBER_STAMP_DWELL_S = 120.0
MIN_SAMPLES = 5


class GateDwell(BaseModel):
    review_id: str
    dwell_s: float
    decision: str


class DwellReport(BaseModel):
    samples: list[GateDwell]
    median_s: float | None = None
    p90_s: float | None = None
    override_rate: float | None = None
    rubber_stamp: bool = False
    notes: list[str] = Field(default_factory=list)


def _ts(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value)


def _review_dwell(review_dir: Path) -> GateDwell | None:
    paused_at = None
    decided_at = None
    decision = ""
    for path in sorted(review_dir.glob("[0-9][0-9]-*.yaml")):
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or "written_at" not in record:
            continue
        node = record.get("node")
        if node == "escalate":
            paused_at = _ts(record["written_at"])
        elif node == "final":
            hitl = record.get("hitl") or {}
            if hitl.get("decision"):
                decided_at = _ts(record["written_at"])
                decision = str(hitl["decision"])
    if paused_at is None or decided_at is None or decided_at < paused_at:
        return None
    return GateDwell(
        review_id=review_dir.name,
        dwell_s=(decided_at - paused_at).total_seconds(),
        decision=decision,
    )


def gate_dwell_report(
    repo_dir: str | Path,
    *,
    rubber_stamp_dwell_s: float = RUBBER_STAMP_DWELL_S,
    min_samples: int = MIN_SAMPLES,
) -> DwellReport:
    reviews_dir = Path(repo_dir) / ".mas" / "reviews"
    samples = []
    if reviews_dir.is_dir():
        for review_dir in sorted(p for p in reviews_dir.iterdir() if p.is_dir()):
            dwell = _review_dwell(review_dir)
            if dwell is not None:
                samples.append(dwell)

    if not samples:
        return DwellReport(
            samples=[],
            notes=["no escalated-and-resumed reviews yet — nothing to measure"],
        )

    dwells = sorted(s.dwell_s for s in samples)
    median = statistics.median(dwells)
    p90 = dwells[min(len(dwells) - 1, int(0.9 * (len(dwells) - 1)))]
    overrides = sum(1 for s in samples if s.decision.startswith("override"))
    override_rate = overrides / len(samples)

    notes = []
    rubber_stamp = False
    if len(samples) < min_samples:
        notes.append(
            f"only {len(samples)} sample(s) (< {min_samples}) — "
            "distribution not yet meaningful"
        )
    elif median < rubber_stamp_dwell_s and override_rate == 0.0:
        rubber_stamp = True
        notes.append(
            f"RUBBER-STAMP PATTERN (F-18.3): median dwell {median:.0f}s < "
            f"{rubber_stamp_dwell_s:.0f}s with zero overrides across "
            f"{len(samples)} escalations — gate decisions are likely not "
            "being read; apply the shed rule (§16.39.3)"
        )
    return DwellReport(
        samples=samples,
        median_s=round(median, 1),
        p90_s=round(p90, 1),
        override_rate=round(override_rate, 3),
        rubber_stamp=rubber_stamp,
        notes=notes,
    )
