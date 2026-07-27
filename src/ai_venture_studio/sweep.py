"""The Sweep role (doc 29, ADR-U36/U37) — janitorial passes over queues
the framework already keeps.

Sweep's inbox is harvested, not invented: expired flags, checkpoint debt,
stale claims, stale capacity entries, watch-item review dates, contract
drift. Allowlisted chore classes may become plan-first patches under the
behavior-preservation contract (out-of-scope diffs abort — invariant
14.29); everything else is a report line. No-action is a recorded,
hash-stamped outcome (invariant 14.30) and over-action — a rising action
rate with a flat debt trend — is the measured failure mode. SW0 is
report-only; promotion is a recorded human decision, demotion on any
contract violation is automatic.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import pathlib
import re

import yaml
from pydantic import BaseModel, Field

SWEEP_CONFIG_FILE = "sweep.yaml"
SWEEP_RUNGS = ("SW0", "SW1", "SW2")
ALLOWLIST = (
    "dependency_upgrade",
    "flag_removal",
    "dead_code_deletion",
    "doc_fixture_refresh",
    "deprecated_references_whittle",
    "ledger_reconciliation",
)
SW1_DEFAULT_CLASS = "flag_removal"  # smallest blast radius (§85.3)


class SweepConfig(BaseModel):
    rung: str = "SW0"
    enabled_classes: list[str] = Field(default_factory=list)
    max_open_prs: int = 2  # E2 solo: 1
    promoted_by: str = ""  # a named human, recorded like a trust promotion


class SweepConfigError(RuntimeError):
    pass


def load_sweep_config(mas_dir: str | pathlib.Path) -> SweepConfig:
    path = pathlib.Path(mas_dir) / SWEEP_CONFIG_FILE
    if not path.exists():
        return SweepConfig()
    raw = yaml.safe_load(path.read_text()) or {}
    config = SweepConfig(**raw)
    if config.rung not in SWEEP_RUNGS:
        raise SweepConfigError(f"rung must be one of {SWEEP_RUNGS}")
    foreign = set(config.enabled_classes) - set(ALLOWLIST)
    if foreign:
        raise SweepConfigError(
            f"classes {sorted(foreign)} are not in the allowlist — Sweep "
            "cannot edit its own allowlist (ADR-U36)")
    if config.rung == "SW0" and config.enabled_classes:
        raise SweepConfigError("SW0 is report-only: no classes may be enabled")
    if config.rung != "SW0" and not config.promoted_by.strip():
        raise SweepConfigError(
            "promotion past SW0 is a recorded human decision (§11.5.1) — "
            "promoted_by is required")
    return config


class Chore(BaseModel):
    queue: str
    chore_class: str
    item: str
    detail: str
    rank: int = 0  # by debt-trend impact; lower = first


class SweepDigest(BaseModel):
    at: str
    rung: str
    items_inspected: int
    chores: list[Chore]
    actionable: list[Chore]  # allowlisted AND rung-enabled, capped
    reported: list[Chore]
    action_rate: float
    snapshot_hash: str
    clean_pass: bool
    note: str = ""


def _watch_items_due(contributing_text: str, today: dt.date) -> list[Chore]:
    chores = []
    for match in re.finditer(r"\|\s*([^|\n]+?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", contributing_text):
        item, review_by = match.group(1).strip(), match.group(2)
        if dt.date.fromisoformat(review_by) <= today:
            chores.append(Chore(
                queue="watch_items", chore_class="ledger_reconciliation",
                item=item, detail=f"review date {review_by} reached — re-verify, "
                                  "update verified_on, or escalate the falsifier"))
    return chores


def harvest_queues(
    workspace: str | pathlib.Path,
    *,
    today: dt.date,
    flag_issues: list = (),
    checkpoint_debt: int = 0,
    stale_claims: list[str] = (),
    stale_capacity: list[str] = (),
    contract_drift: list[dict] = (),
    contributing_text: str = "",
) -> list[Chore]:
    """The inbox, from ledgers the canon already keeps (§84.2). Callers
    feed the outputs of the existing linters; Sweep invents nothing."""
    chores: list[Chore] = []
    for issue in flag_issues:
        if getattr(issue, "rule", "") in ("expired_blocking", "expired_grace"):
            chores.append(Chore(
                queue="flags", chore_class="flag_removal", item=issue.flag,
                detail="execute the removal task scheduled at creation (ADR-U35)",
                rank=0 if issue.rule == "expired_blocking" else 1))
    if checkpoint_debt:
        chores.append(Chore(
            queue="deprecated_references",
            chore_class="deprecated_references_whittle",
            item=f"{checkpoint_debt} baseline violations",
            detail="whittle N items this pass; the count must trend down (F-28.1)",
            rank=2))
    for claim_id in stale_claims:
        chores.append(Chore(
            queue="claim_ledger", chore_class="ledger_reconciliation",
            item=claim_id, detail="expired evidence: re-snapshot or retire the "
                                  "claim visibly (§20.53)", rank=1))
    for endpoint in stale_capacity:
        chores.append(Chore(
            queue="capacity", chore_class="ledger_reconciliation", item=endpoint,
            detail="measured.at predates the last perf-relevant merge — "
                   "schedule a re-run; stale meanwhile (§77.4)", rank=2))
    for finding in contract_drift:
        chores.append(Chore(
            queue="stream_contracts", chore_class="ledger_reconciliation",
            item=str(finding.get("topic", "?")),
            detail=str(finding.get("message", "drift")), rank=1))
    chores += _watch_items_due(contributing_text, today)
    return sorted(chores, key=lambda c: (c.rank, c.queue, c.item))


class ContractCheck(BaseModel):
    chore_class: str
    files_touched: list[str]
    declared_scope: list[str]
    suite_green: bool
    coverage_delta: float  # negative = decreased
    api_surface_unchanged: bool
    baselines_untouched: bool  # replay-identity + eval-gate


def behavior_preservation_check(check: ContractCheck) -> list[str]:
    """Invariant 14.29: any failure aborts the PR — the change exits to the
    normal pipeline as a proposed brief instead."""
    failures = []
    if check.chore_class not in ALLOWLIST:
        failures.append(f"chore class {check.chore_class!r} is not allowlisted")
    foreign = [f for f in check.files_touched
               if not any(f == s or f.startswith(s.rstrip("*")) for s in check.declared_scope)]
    if foreign:
        failures.append(f"diff outside declared scope: {foreign} — not a sweep task")
    if not check.suite_green:
        failures.append("hermetic suite not green")
    if check.coverage_delta < 0:
        failures.append(f"coverage decreased ({check.coverage_delta:+.2%})")
    if not check.api_surface_unchanged:
        failures.append("declared api_surface changed — behavior, not janitorial")
    if not check.baselines_untouched:
        failures.append("replay-identity/eval-gate baselines touched")
    return failures


def run_sweep_pass(
    workspace: str | pathlib.Path,
    chores: list[Chore],
    *,
    config: SweepConfig,
    at: str,
) -> SweepDigest:
    snapshot = yaml.safe_dump([c.model_dump() for c in chores], sort_keys=True)
    snapshot_hash = "sha256:" + hashlib.sha256(snapshot.encode()).hexdigest()
    enabled = (set() if config.rung == "SW0"
               else {SW1_DEFAULT_CLASS} & set(config.enabled_classes)
               if config.rung == "SW1" and not config.enabled_classes
               else set(config.enabled_classes) if config.rung == "SW2"
               else set(config.enabled_classes[:1]))
    eligible = [c for c in chores if c.chore_class in enabled]
    actionable = eligible[: config.max_open_prs]  # the attention cap (14.30)
    reported = [c for c in chores if c not in actionable]
    digest = SweepDigest(
        at=at, rung=config.rung, items_inspected=len(chores),
        chores=chores, actionable=actionable, reported=reported,
        action_rate=len(actionable) / len(chores) if chores else 0.0,
        snapshot_hash=snapshot_hash,
        clean_pass=not chores,
        note=("clean pass — recorded, not silent (invariant 14.30)" if not chores
              else f"{len(actionable)} patch(es) within the cap of "
                   f"{config.max_open_prs}; {len(reported)} reported"))
    out = pathlib.Path(workspace) / ".mas" / "sweep"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"digest-{at}.yaml").write_text(
        yaml.safe_dump(digest.model_dump(), sort_keys=False))
    return digest


def over_action_alarm(
    previous: SweepDigest, current: SweepDigest, *, debt_delta: int
) -> bool:
    """A rising action rate with a flat-or-growing debt trend is churn, not
    cleanliness — a compounding-loop finding (§85.2)."""
    return current.action_rate > previous.action_rate and debt_delta >= 0
