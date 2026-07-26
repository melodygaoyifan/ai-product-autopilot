"""The shared product-stage engine (§12.24.1, applied to P-stages).

generate → deterministic tools → critique-vote → verify → leader → gate,
with deterministic control flow throughout: the LLM writes and judges,
Python decides what runs next (CLAUDE.md architecture invariant). Voters
are loaded from their skills/product/<stage>/ charters, run independently
with no cross-visibility, and every finding passes a fresh verify seat
before the Leader sees it. Deterministic tool findings feed the writer's
revision loop directly — a machine-checkable failure is feedback, not a
report.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from typing import Callable

import yaml
from pydantic import BaseModel, Field

from autoproduct.providers import get_provider
from autoproduct.yamlx import extract_mapping

PRODUCT_VOTER_MARKER = "PRODUCT-STAGE VOTER"
PRODUCT_VERIFIER_MARKER = "PRODUCT-STAGE VERIFIER"
PRODUCT_LEADER_MARKER = "PRODUCT-STAGE LEADER"

MAX_REVISIONS = 2

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

_VOTER_CONTRACT = """

Respond with ONLY YAML:
findings:
  - severity: major|minor
    problem: one sentence
    evidence: verbatim quote from the artifact that grounds the finding
"""

_VERIFIER_SYSTEM = f"""You are the {PRODUCT_VERIFIER_MARKER}: a fresh agent
re-deriving one voter finding from the artifact alone. Verify it only if the
quoted evidence appears and supports the problem stated; refute plausible-
but-wrong findings without mercy.

Respond with ONLY YAML:
verdict: verified|refuted
reason: one sentence
"""

_LEADER_SYSTEM = f"""You are the {PRODUCT_LEADER_MARKER}: synthesize the
verified findings into the gate surface. Never add findings of your own;
never soften a major.

Respond with ONLY YAML:
summary: two sentences for the human at the gate
"""


class VoterFinding(BaseModel):
    voter: str
    severity: str
    problem: str
    evidence: str = ""
    verified: bool = False


class StageReport(BaseModel):
    stage: str
    status: str  # ok | gate_blocked | needs_revision
    revisions: int
    det_findings: list[dict] = Field(default_factory=list)
    voter_findings: list[VoterFinding] = Field(default_factory=list)
    leader_summary: str = ""
    gate: dict = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)


@dataclass
class StageSpec:
    """Everything that differs between P-stages; the engine is the same."""

    name: str
    writer_system: str
    expected_keys: tuple[str, ...]
    skills_subdir: str  # under skills/product/
    # dict from the writer → (artifact object, artifact_text for voters).
    # Raises ValueError on schema violations (feeds the revision loop).
    parse: Callable[[dict], tuple[object, str]]
    # deterministic checks: artifact → list of {rule, message} dicts.
    det_tools: Callable[[object], list[dict]]
    # gate: artifact → {"passed": bool, ...surface}
    gate: Callable[[object], dict]
    # persist artifact; returns written paths.
    persist: Callable[[object, str], list[str]] = field(
        default=lambda artifact, workspace: []
    )


def _default_skills_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[3] / "skills" / "product"


def load_voter_charters(
    stage_subdir: str, skills_root: pathlib.Path | None = None
) -> list[tuple[str, str]]:
    """(name, system_prompt) per charter file; the frontmatter contract is
    honored for identity, the body becomes the seat's system prompt."""
    root = (skills_root or _default_skills_root()) / stage_subdir
    voters = []
    for path in sorted(root.glob("*.md")):
        text = path.read_text()
        match = _FRONTMATTER.match(text)
        name = path.stem
        if match:
            meta = yaml.safe_load(match.group(1)) or {}
            name = str(meta.get("name", name))
            text = text[match.end():]
        voters.append(
            (name, f"You are a {PRODUCT_VOTER_MARKER}.\n\n{text}{_VOTER_CONTRACT}")
        )
    return voters


def run_product_stage(
    spec: StageSpec,
    user_input: str,
    workspace: str,
    *,
    provider: str = "anthropic",
    writer_model: str = "claude-opus-4-8",
    voter_model: str = "claude-sonnet-5",
    skills_root: pathlib.Path | None = None,
) -> StageReport:
    provider_impl = get_provider(provider)

    artifact: object | None = None
    artifact_text = ""
    det_findings: list[dict] = []
    feedback = ""
    revision = 0
    for revision in range(MAX_REVISIONS + 1):
        raw = provider_impl.complete(
            model=writer_model,
            system=spec.writer_system,
            user=user_input
            + (f"\n\n<revision_feedback>\n{feedback}\n</revision_feedback>" if feedback else ""),
            max_tokens=8192,
        )
        try:
            data = extract_mapping(raw, spec.expected_keys)
        except ValueError:
            feedback = (
                "Your previous response was not a parseable YAML mapping. "
                "Respond with ONLY the YAML schema given, double-quoting "
                "every string value."
            )
            artifact = None
            continue
        try:
            artifact, artifact_text = spec.parse(data)
        except ValueError as exc:
            feedback = f"schema violation: {exc}"
            artifact = None
            continue
        det_findings = spec.det_tools(artifact)
        if not det_findings:
            break
        # Deterministic failures are revision feedback (ADR-U05): the
        # writer gets the machine's findings verbatim, once per revision.
        feedback = yaml.safe_dump({"deterministic_findings": det_findings},
                                  sort_keys=False, allow_unicode=True)
    if artifact is None:
        raise ValueError(
            f"{spec.name}: writer failed schema after {MAX_REVISIONS + 1} "
            f"attempts: {feedback}"
        )

    # Voters: independent seats, no cross-visibility, then a fresh verify
    # pass per finding — plausible-but-wrong findings die here.
    voter_findings: list[VoterFinding] = []
    for voter_name, system in load_voter_charters(spec.skills_subdir, skills_root):
        raw = provider_impl.complete(
            model=voter_model, system=system, user=artifact_text, max_tokens=2048
        )
        try:
            found = extract_mapping(raw, ("findings",)).get("findings") or []
        except ValueError:
            continue  # a voter that cannot emit the contract contributes nothing
        for entry in found[:5]:
            if not isinstance(entry, dict) or not entry.get("problem"):
                continue
            finding = VoterFinding(
                voter=voter_name,
                severity=str(entry.get("severity", "minor")),
                problem=str(entry["problem"]),
                evidence=str(entry.get("evidence", "")),
            )
            raw_verdict = provider_impl.complete(
                model=voter_model,
                system=_VERIFIER_SYSTEM,
                user=yaml.safe_dump(
                    {"finding": finding.model_dump(exclude={"verified"}),
                     "artifact": artifact_text},
                    sort_keys=False, allow_unicode=True,
                ),
                max_tokens=512,
            )
            try:
                verdict = extract_mapping(raw_verdict, ("verdict",))
            except ValueError:
                verdict = {}
            finding.verified = verdict.get("verdict") == "verified"
            if finding.verified:
                voter_findings.append(finding)

    raw_summary = provider_impl.complete(
        model=writer_model,
        system=_LEADER_SYSTEM,
        user=yaml.safe_dump(
            {"stage": spec.name,
             "verified_findings": [f.model_dump() for f in voter_findings],
             "det_findings": det_findings},
            sort_keys=False, allow_unicode=True,
        ),
        max_tokens=1024,
    )
    try:
        leader_summary = str(extract_mapping(raw_summary, ("summary",))["summary"])
    except (ValueError, KeyError):
        leader_summary = f"{len(voter_findings)} verified finding(s); see report."

    gate = spec.gate(artifact)
    majors = [f for f in voter_findings if f.severity == "major"]
    if det_findings or not gate.get("passed"):
        status = "gate_blocked"
    elif majors:
        status = "needs_revision"
    else:
        status = "ok"
    return StageReport(
        stage=spec.name,
        status=status,
        revisions=revision,
        det_findings=det_findings,
        voter_findings=voter_findings,
        leader_summary=leader_summary,
        gate=gate,
        artifacts=spec.persist(artifact, workspace),
    )
