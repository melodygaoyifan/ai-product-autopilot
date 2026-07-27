"""Gate R — regulated change control as an external gate (§18.47.3, ADR-U14
mechanics pointed at internal bureaucracy).

Entry = change package + preflight checklist 100% green. The checklist is
the mechanizable shadow of the CAB's rules; every rejection sharpens it:
mechanizable reasons become checklist fixtures, the rest become
compounding-loop entries. Submission itself is human-only — there is no
submit function in this module by design (forbidden_autonomous:
cab_submission).
"""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

PREFLIGHT_PATH = ".mas/cab-preflight.yaml"
REJECTIONS_PATH = ".mas/cab-rejections.yaml"

FORBIDDEN_AUTONOMOUS = ("cab_submission",)


class ChangePackage(BaseModel):
    """What goes in front of the CAB — assembled by the pipeline, submitted
    by a human."""

    change_id: str
    description: str = ""
    rollback_plan: str = ""
    affected_systems: list[str] = Field(default_factory=list)
    evidence_bundle: str = Field(
        default="", description="Path to the exported evidence bundle"
    )
    approver_role: str = ""
    required_role: str = ""


class PreflightCheck(BaseModel):
    id: str
    description: str
    source: str = "template"  # template | rejection:<change_id>
    evaluator: list[str] = Field(
        default_factory=list,
        description="Graduation path for rejection-sourced checks: argv run "
        "with the change-package JSON appended as the final argument; exit 0 "
        "= pass. Empty = manual attestation required. A missing evaluator "
        "binary FAILS the check — an unrunnable evaluator never reads as "
        "attested.",
    )


class PreflightResult(BaseModel):
    check: PreflightCheck
    passed: bool
    detail: str = ""


class GateREntry(BaseModel):
    change_id: str
    eligible: bool
    results: list[PreflightResult]

    @property
    def failures(self) -> list[PreflightResult]:
        return [r for r in self.results if not r.passed]


# Starter shadow of a generic ITGC change checklist (§19 G2 Day 8);
# project-extendable via .mas/cab-preflight.yaml, like .mas/spec-lint.yaml.
_TEMPLATE_CHECKS = [
    PreflightCheck(id="change_record", description="Change description present"),
    PreflightCheck(id="rollback_plan", description="Rollback plan present"),
    PreflightCheck(id="affected_systems", description="Affected-system inventory non-empty"),
    PreflightCheck(id="evidence_bundle", description="Evidence bundle attached and readable"),
    PreflightCheck(id="approver_role", description="Approver role matches the required role"),
]


def load_preflight_checklist(repo_dir: str | Path) -> list[PreflightCheck]:
    """Template checks plus any accumulated rejection fixtures."""
    checks = list(_TEMPLATE_CHECKS)
    path = Path(repo_dir) / PREFLIGHT_PATH
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for item in data.get("checks", []):
            checks.append(PreflightCheck(**item))
    return checks


def _evaluate(check: PreflightCheck, package: ChangePackage, repo_dir: Path) -> PreflightResult:
    ok, detail = True, ""
    if check.id == "change_record":
        ok = bool(package.description.strip())
    elif check.id == "rollback_plan":
        ok = bool(package.rollback_plan.strip())
    elif check.id == "affected_systems":
        ok = bool(package.affected_systems)
    elif check.id == "evidence_bundle":
        bundle = Path(package.evidence_bundle)
        if not bundle.is_absolute():
            bundle = repo_dir / bundle
        ok = bool(package.evidence_bundle) and bundle.exists()
        detail = "" if ok else f"not found: {package.evidence_bundle or '(unset)'}"
    elif check.id == "approver_role":
        ok = bool(package.approver_role) and package.approver_role == package.required_role
        if not ok:
            detail = f"approver={package.approver_role or '(unset)'} required={package.required_role or '(unset)'}"
    elif check.evaluator:
        ok, detail = _run_evaluator(check, package, repo_dir)
    else:
        # Rejection-sourced fixtures start life as manual attestations: the
        # gate surfaces them for the human preparing the submission. They
        # graduate to mechanized checks when someone adds an `evaluator`
        # argv to the check in .mas/cab-preflight.yaml.
        ok, detail = False, "manual attestation required (rejection-sourced check)"
    return PreflightResult(check=check, passed=ok, detail=detail)


def _run_evaluator(
    check: PreflightCheck, package: ChangePackage, repo_dir: Path
) -> tuple[bool, str]:
    import shutil
    import subprocess

    executable = shutil.which(check.evaluator[0])
    if executable is None:
        return False, (
            f"evaluator {check.evaluator[0]!r} not on PATH — an unrunnable "
            "evaluator never reads as attested"
        )
    argv = [executable, *check.evaluator[1:], package.model_dump_json()]
    try:
        proc = subprocess.run(
            argv, cwd=str(repo_dir), capture_output=True, text=True, timeout=120
        )
    except subprocess.TimeoutExpired:
        return False, "evaluator timed out after 120s"
    if proc.returncode == 0:
        return True, ""
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return False, f"evaluator exit {proc.returncode}: {output[:200]}"


def gate_r_entry(repo_dir: str | Path, package: ChangePackage) -> GateREntry:
    """Entry precondition only — approval and submission stay human."""
    root = Path(repo_dir)
    results = [
        _evaluate(check, package, root)
        for check in load_preflight_checklist(root)
    ]
    return GateREntry(
        change_id=package.change_id,
        eligible=all(r.passed for r in results),
        results=results,
    )


def prepare_change_package(
    repo_dir: str | Path, review_id: str, change_id: str | None = None
) -> ChangePackage:
    """Review → CAB-ready package in one call: exports the evidence bundle
    and pre-fills what the audit trail knows. The human parts stay empty on
    purpose — rollback plan and approver are decisions, not derivations —
    so a fresh package is NOT gate-eligible until a person completes it."""
    from ai_venture_studio.adoption.evidence import write_evidence_bundle

    root = Path(repo_dir)
    finals = sorted((root / ".mas" / "reviews" / review_id).glob("[0-9][0-9]-final.yaml"))
    if not finals:
        raise FileNotFoundError(
            f"review {review_id} has no final mirror record — an unfinished "
            "review is not CAB-ready"
        )
    final = yaml.safe_load(finals[-1].read_text(encoding="utf-8"))
    bundle_path = write_evidence_bundle(root, review_id)

    config = {}
    preflight = root / PREFLIGHT_PATH
    if preflight.exists():
        config = yaml.safe_load(preflight.read_text(encoding="utf-8")) or {}

    return ChangePackage(
        change_id=change_id or review_id,
        description=(
            f"{final.get('target', '?')} — {final.get('verdict', '?')}: "
            f"{final.get('summary', '')}"
        ),
        affected_systems=list(final.get("deploy_review_recommended") or []),
        evidence_bundle=str(bundle_path.relative_to(root)),
        required_role=str(config.get("required_role", "")),
    )


def save_change_package(repo_dir: str | Path, package: ChangePackage) -> Path:
    out_dir = Path(repo_dir) / ".mas" / "cab"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{package.change_id}.yaml"
    path.write_text(
        yaml.safe_dump(package.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def record_rejection(
    repo_dir: str | Path, change_id: str, reasons: list[dict]
) -> dict[str, int]:
    """A rejection is structured input (§41.3): each reason dict is
    {reason: str, mechanizable: bool}. Mechanizable reasons append preflight
    fixtures; the rest land in the rejections log the compounding loop reads."""
    root = Path(repo_dir)
    fixtures, loop_entries = 0, 0

    preflight = root / PREFLIGHT_PATH
    preflight.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if preflight.exists():
        data = yaml.safe_load(preflight.read_text(encoding="utf-8")) or {}
    checks = data.setdefault("checks", [])

    log = root / REJECTIONS_PATH
    log_data = {}
    if log.exists():
        log_data = yaml.safe_load(log.read_text(encoding="utf-8")) or {}
    entries = log_data.setdefault("rejections", [])

    stamp = datetime.datetime.now(datetime.UTC).isoformat()
    for i, item in enumerate(reasons):
        reason = str(item.get("reason", "")).strip()
        if not reason:
            raise ValueError(f"rejection reason {i} for {change_id} is empty")
        if item.get("mechanizable"):
            checks.append(
                {
                    "id": f"rej_{change_id}_{i}",
                    "description": reason,
                    "source": f"rejection:{change_id}",
                }
            )
            fixtures += 1
        else:
            entries.append(
                {"change_id": change_id, "reason": reason, "recorded_at": stamp}
            )
            loop_entries += 1

    if fixtures:
        preflight.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    if loop_entries:
        log.write_text(
            yaml.safe_dump(log_data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    return {"preflight_fixtures": fixtures, "compounding_entries": loop_entries}
