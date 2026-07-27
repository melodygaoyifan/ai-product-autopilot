"""Deployment Review MAS (§09.11) — insight/assistive tiers.

Reuses the review-stage machinery wholesale: the same Voter class over a
deploy-specific skills directory, the same fresh-agent verification, the
same scoring. What differs is the verdict taxonomy and the policy input:

- Policy-as-Prompt: `.mas/deploy-policy.yaml` is compiled into voter
  context, and its `forbidden` entries are enforced deterministically too.
- Trust tier ceiling: this stage RECOMMENDS. PROMOTE means "nothing blocks
  promotion", never "promoted" — production deploys stay human-executed
  forever (§08.1.8, hard architectural ceiling).

This module holds the stage's primitives (policy, verdict taxonomy,
deterministic enforcement); the checkpointed orchestration lives in
`deploy/graph.py` since v0.32 (plan D15) — `run_deploy_review` is
re-exported from there unchanged.
"""

from __future__ import annotations

import enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ai_venture_studio.diff import ParsedDiff
from ai_venture_studio.state import Severity, VoterFinding

DEFAULT_POLICY = {
    "tier": "insight",  # insight | assistive (autonomous requires track record, v0.8+)
    "forbidden": [
        "permissions: write-all",
        "pull_request_target",
        "--privileged",
    ],
    "require_rollback_note": True,
}


class DeployVerdict(str, enum.Enum):
    PROMOTE = "PROMOTE"  # recommendation only — human executes
    HOLD_FOR_HUMAN = "HOLD_FOR_HUMAN"
    ESCALATE_DEPLOY_RISK = "ESCALATE_DEPLOY_RISK"
    ESCALATE_MIGRATION_DESTRUCTIVE = "ESCALATE_MIGRATION_DESTRUCTIVE"
    ESCALATE_POLICY_VIOLATION = "ESCALATE_POLICY_VIOLATION"


class DeployResult(BaseModel):
    verdict: DeployVerdict
    tier: str
    summary: str
    findings: list[VoterFinding] = Field(default_factory=list)
    blocked_voters: list[str] = Field(default_factory=list)
    deploy_files: list[str] = Field(default_factory=list)
    artifacts_dir: str = ""
    branch: str = Field(
        default="",
        description="the branch this review covers, resolved at run time; "
        "empty means unresolvable, which `deploy-execute` treats as a refusal "
        "rather than assuming a default (ADR-031)",
    )


def load_policy(repo_dir: str | Path) -> dict:
    path = Path(repo_dir) / ".mas" / "deploy-policy.yaml"
    if not path.exists():
        return dict(DEFAULT_POLICY)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {**DEFAULT_POLICY, **loaded}


def _policy_prompt(policy: dict) -> str:
    forbidden = "\n".join(f"- {f}" for f in policy["forbidden"])
    return (
        "Deploy policy for this project (violations are findings of severity "
        f"critical, taxonomy_hint 'deploy:policy'):\nForbidden patterns:\n{forbidden}\n"
        + (
            "Every migration must state its rollback path in the PR.\n"
            if policy.get("require_rollback_note")
            else ""
        )
    )


def _policy_violations(diff: ParsedDiff, policy: dict) -> list[VoterFinding]:
    """The deterministic half of Policy-as-Prompt: `forbidden` strings are
    enforced by code even if every voter misses them."""
    findings = []
    for file in diff.files:
        for lineno, text in file.added:
            for forbidden in policy["forbidden"]:
                if forbidden in text:
                    findings.append(
                        VoterFinding(
                            voter="tool:deploy_policy",
                            title=f"Forbidden by deploy policy: {forbidden}",
                            severity=Severity.CRITICAL,
                            confidence="certain",
                            file_path=file.path,
                            line_start=lineno,
                            line_end=lineno,
                            evidence=text.strip()[:200],
                            explanation="This exact pattern is on the project's "
                            "deploy-policy forbidden list (.mas/deploy-policy.yaml).",
                            taxonomy_hint="deploy:policy",
                            verification="VERIFIED",
                            score=100,
                        )
                    )
    return findings


def decide(findings: list[VoterFinding], blocked: list[str]) -> DeployVerdict:
    """Deterministic verdict selection — priority order mirrors §09.11.6."""
    hints = {f.taxonomy_hint for f in findings}
    if "deploy:policy" in hints:
        return DeployVerdict.ESCALATE_POLICY_VIOLATION
    if any(
        f.taxonomy_hint == "deploy:migration" and f.severity is Severity.CRITICAL
        for f in findings
    ):
        return DeployVerdict.ESCALATE_MIGRATION_DESTRUCTIVE
    if any(f.severity in (Severity.CRITICAL, Severity.HIGH) for f in findings):
        return DeployVerdict.ESCALATE_DEPLOY_RISK
    if findings or len(blocked) >= 2:
        return DeployVerdict.HOLD_FOR_HUMAN
    return DeployVerdict.PROMOTE
