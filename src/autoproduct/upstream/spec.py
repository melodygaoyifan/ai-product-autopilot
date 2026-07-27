"""Spec stage (§13, built first per doc 14) — the anchor artifact.

generate → deterministic checks (ears_lint + coverage matrix) → critique
voters (Testability, Ambiguity) → bounded revision (fresh context, ≤2) →
Gate U3 (human approval). A spec that fails its deterministic checks after
revision is saved as `blocked`, never silently approved.

The spec is what `build` implements test-first and what the review stage
later verifies against — machine-checkable EARS criteria, a test skeleton
per criterion, and the domain profile's extras baked in.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from autoproduct.providers import get_provider
from autoproduct.upstream import ears
from autoproduct.upstream.workspace import Project, load_project
from autoproduct.yamlx import extract_mapping

SPECWRITER_MARKER = "spec writer for a greenfield product system"

MAX_REVISIONS = 2


class TestSkeleton(BaseModel):
    path: str
    purpose: str
    covers: list[int] = Field(description="indices into criteria (0-based)")


class Spec(BaseModel):
    slug: str
    title: str
    status: str = "proposed"  # proposed | approved | blocked
    request: str
    profile: str
    design: str
    criteria: list[str]
    test_skeletons: list[TestSkeleton]
    lint_issues: list[dict] = Field(default_factory=list)
    critic_issues: list[dict] = Field(default_factory=list)
    block_reasons: list[str] = Field(
        default_factory=list,
        description="why status is 'blocked' — empty when proposed; a "
        "gap-blocked spec used to surface as the useless 'lint 0 issue(s)'",
    )
    revisions: int = 0
    built: bool = False
    approved_hash: str = Field(
        default="",
        description="§13.35.5: hash of the contract slice at Gate U3 approval. "
        "A later mismatch means someone edited a frozen spec outside the SCR "
        "channel, and the build refuses the unratified fork.",
    )


_WRITER_SYSTEM = f"""You are the {SPECWRITER_MARKER}. Produce a buildable
feature spec for the request, honoring the project constraints and profile
extras provided.

Rules:
- Acceptance criteria MUST use EARS syntax (The/When/While/If-then/Where
  ... shall ...) and measurable conditions — never vague words like
  "fast" or "user-friendly".
- Every criterion must be covered by at least one test skeleton (covers
  lists criterion indices, 0-based). Test paths live under tests/.
- The design section states the module layout and, where the profile
  demands it, API contracts / domains / permissions.
- Smallest spec that satisfies the request; no speculative features.
- The request's scope is law: a capability it explicitly excludes or
  defers must not appear in the spec. A profile constraint about an
  excluded capability is inapplicable — never a reason to add it.
- Test skeletons assert observable behavior (status codes, response
  bodies, rendered text, the PRESENCE of a labeled control) — never
  markup microstructure like specific id/class/attribute values.
- Where the project context includes a source_contract, that is the
  founder's LITERAL interface contract: reproduce its exact paths,
  methods, field names, and enumerated values verbatim in the design
  and criteria. Never rename, split, add to, or generalize them — a
  field the contract calls "name" stays "name"; a value it writes as
  "day5" stays the string "day5". The probes that judge the product
  are written from that contract, not from your spec.

Respond with ONLY YAML:
title: ...
design: |
  ...
criteria:
  - "When ..., the system shall ..."
test_skeletons:
  - path: tests/test_x.py
    purpose: ...
    covers: [0, 1]
"""

def contract_hash(spec: "Spec") -> str:
    """Hash of what Gate U3 actually approved: the contract a human read.

    Deliberately excludes bookkeeping (status, built, revisions, critic
    notes) — those move for legitimate reasons and would make every build
    look like a fork.
    """
    import hashlib

    payload = yaml.safe_dump(
        {
            "title": spec.title,
            "design": spec.design,
            "criteria": list(spec.criteria),
            "test_skeletons": [s.model_dump() for s in spec.test_skeletons],
        },
        sort_keys=True, allow_unicode=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "feature"


def _coverage_gaps(spec_data: dict) -> list[int]:
    covered = {
        i
        for skeleton in spec_data.get("test_skeletons", [])
        for i in skeleton.get("covers", [])
    }
    return [i for i in range(len(spec_data.get("criteria", []))) if i not in covered]


def run_spec_stage(
    repo_dir: str | Path,
    request: str,
    *,
    provider: str = "anthropic",
    writer_model: str = "claude-opus-4-8",
    critic_model: str = "claude-sonnet-5",
    source_contract: str = "",
) -> Spec:
    project: Project = load_project(repo_dir)
    if not source_contract:
        # The founder's FDR, when the workspace carries one, IS the
        # interface contract. Without it the writer only ever sees the
        # planner's paraphrase and re-invents field names and enums the
        # probes then reject (product-bench run 5, case 04: FDR said
        # {"name"} and "day5"; the built API demanded "direction" and
        # integer rounds — every probe 400'd).
        fdr_file = Path(repo_dir) / "FDR.md"
        if fdr_file.exists():
            source_contract = fdr_file.read_text(encoding="utf-8")
    provider_impl = get_provider(provider)
    profile = project.profile_data
    design_memory = ""
    design_path = Path(repo_dir) / "product" / "design.md"
    if design_path.exists():
        design_memory = design_path.read_text(encoding="utf-8")[-4000:]
    context = yaml.safe_dump(
        {
            "project": project.name,
            "profile": project.profile,
            "constraints": profile.get("constraints", []),
            "spec_extras": profile.get("spec_extras", []),
            "stack_hint": profile.get("stack_hint", ""),
        },
        sort_keys=False, allow_unicode=True,
    ) + (
        f"\nexisting_architecture: |\n  (extend this — do not re-derive)\n{design_memory}"
        if design_memory
        else ""
    ) + (
        f"\nsource_contract: |\n  (the founder's literal interface contract — "
        f"reproduce exact paths, methods, field names, and values verbatim)\n"
        + "".join(f"  {line}\n" for line in source_contract[:3000].splitlines())
        if source_contract.strip()
        else ""
    )

    feedback = ""
    spec_data: dict = {}
    lint: list = []
    critics: list[dict] = []
    for revision in range(MAX_REVISIONS + 1):
        raw = provider_impl.complete(
            model=writer_model,
            system=_WRITER_SYSTEM,
            user=f"<project>\n{context}</project>\n\n<request>\n{request}\n</request>"
            + (f"\n\n<revision_feedback>\n{feedback}\n</revision_feedback>" if feedback else ""),
            max_tokens=4096,
        )
        try:
            spec_data = extract_mapping(raw, ("criteria", "title"))
        except ValueError:
            feedback = (
                "Your previous response was not a parseable YAML mapping. "
                "Respond with ONLY the YAML schema given, and double-quote "
                "every string value."
            )
            spec_data = {}
            lint, critics = [], []
            continue
        lint = ears.lint_criteria([str(c) for c in spec_data.get("criteria", [])])
        gaps = _coverage_gaps(spec_data)
        # Charter roster (doc 13 §25.1): Testability, Consistency,
        # Completeness, Ambiguity, InterfaceImpact — the two ad-hoc critic
        # prompts retired here (plan phase D13). The roster sees the same
        # slice the old critics did, plus the contract InterfaceImpact
        # judges fidelity against.
        from autoproduct.product.stage_engine import run_critique_roster
        from autoproduct.product.voter_gate import family_roots

        skills_root, _ = family_roots("spec")
        roster = run_critique_roster(
            "spec", "spec",
            yaml.safe_dump(
                {"criteria": spec_data.get("criteria", []),
                 "test_skeletons": spec_data.get("test_skeletons", []),
                 "design": str(spec_data.get("design", "")),
                 "source_contract": source_contract[:3000]},
                sort_keys=False, allow_unicode=True,
            ),
            str(repo_dir),
            provider_impl=provider_impl,
            voter_model=critic_model,
            leader_model=writer_model,
            skills_root=skills_root,
            det_findings=[i.model_dump() for i in lint],
        )
        critics = roster.as_issues()[:10]
        majors = [c for c in critics if c.get("severity") == "major"]
        if not lint and not gaps and not majors:
            break
        feedback = yaml.safe_dump(
            {
                "ears_lint": [i.model_dump() for i in lint],
                "uncovered_criteria_indices": gaps,
                "critic_majors": majors,
            },
            sort_keys=False, allow_unicode=True,
        )
    else:
        pass

    gaps = _coverage_gaps(spec_data)
    has_criteria = bool(spec_data.get("criteria"))
    status = "proposed" if has_criteria and not lint and not gaps else "blocked"
    block_reasons: list[str] = []
    if status == "blocked":
        if not has_criteria:
            block_reasons.append("no acceptance criteria")
        if lint:
            block_reasons.append(
                f"{len(lint)} EARS lint issue(s): "
                + "; ".join(str(i.problem)[:80] for i in lint[:3])
            )
        if gaps:
            block_reasons.append(
                f"criteria {', '.join(str(g) for g in gaps)} covered by no "
                "test skeleton"
            )
    slug = _slugify(str(spec_data.get("title") or request))

    # SCR guard (ADR-U02): overwriting a spec that has been BUILT is the
    # drift this system kills — the only legal channel is an approved SCR,
    # and each approval grants exactly one regeneration.
    existing_path = _spec_dir(repo_dir, slug) / "spec.yaml"
    if existing_path.exists():
        existing = yaml.safe_load(existing_path.read_text(encoding="utf-8")) or {}
        if existing.get("built") and not _scr_grant(repo_dir, slug):
            raise PermissionError(
                f"spec {slug!r} is built and frozen; changing it requires an "
                f"approved SCR: autoproduct scr {slug} \"<reason>\" then "
                "autoproduct scr-approve <n>"
            )
    spec = Spec(
        slug=slug,
        title=str(spec_data.get("title", request))[:120],
        status=status,
        request=request,
        profile=project.profile,
        design=str(spec_data.get("design", "")),
        criteria=[str(c) for c in spec_data.get("criteria", [])],
        test_skeletons=[
            TestSkeleton.model_validate(s) for s in spec_data.get("test_skeletons", [])
        ],
        lint_issues=[i.model_dump() for i in lint],
        critic_issues=critics,
        block_reasons=block_reasons,
        revisions=revision,
    )
    _save(repo_dir, spec)
    return spec


def _spec_dir(repo_dir: str | Path, slug: str) -> Path:
    return Path(repo_dir) / "specs" / slug


def _save(repo_dir: str | Path, spec: Spec) -> None:
    directory = _spec_dir(repo_dir, spec.slug)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "spec.yaml").write_text(
        yaml.safe_dump(spec.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    criteria = "\n".join(f"{i}. {c}" for i, c in enumerate(spec.criteria))
    skeletons = "\n".join(
        f"- `{s.path}` — {s.purpose} (covers {s.covers})" for s in spec.test_skeletons
    )
    (directory / "spec.md").write_text(
        f"# {spec.title}\n\nstatus: **{spec.status}** · profile: {spec.profile} · "
        f"revisions: {spec.revisions}\n\n## Design\n\n{spec.design}\n\n"
        f"## Acceptance criteria (EARS)\n\n{criteria}\n\n"
        f"## Test skeletons\n\n{skeletons}\n\n"
        f"Approve with: `autoproduct spec-approve {spec.slug}` (Gate U3)\n",
        encoding="utf-8",
    )


def load_spec(repo_dir: str | Path, slug: str) -> Spec:
    path = _spec_dir(repo_dir, slug) / "spec.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no spec {slug!r} under {repo_dir}/specs")
    return Spec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _scr_dir(repo_dir: str | Path) -> Path:
    return Path(repo_dir) / ".mas" / "scr"


def _scr_grant(repo_dir: str | Path, slug: str) -> bool:
    """An approved, unconsumed SCR for this spec grants one regeneration."""
    for path in sorted(_scr_dir(repo_dir).glob("SCR-*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("spec_slug") == slug and data.get("status") == "approved":
            data["status"] = "consumed"
            path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
            return True
    return False


def raise_scr(repo_dir: str | Path, slug: str, reason: str) -> Path:
    """ADR-U02: the only legal drift channel after a spec is built."""
    directory = _scr_dir(repo_dir)
    directory.mkdir(parents=True, exist_ok=True)
    number = len(list(directory.glob("SCR-*.yaml"))) + 1
    path = directory / f"SCR-{number:03d}.yaml"
    path.write_text(
        yaml.safe_dump(
            {"number": number, "spec_slug": slug, "reason": reason, "status": "proposed"},
            sort_keys=False, allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return path


def approve_scr(repo_dir: str | Path, number: int) -> dict:
    """The human half of the SCR channel."""
    path = _scr_dir(repo_dir) / f"SCR-{number:03d}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no SCR-{number:03d}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["status"] = "approved"
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return data


def approve_spec(repo_dir: str | Path, slug: str) -> Spec:
    """Gate U3 — the human acknowledgement that makes a spec buildable."""
    spec = load_spec(repo_dir, slug)
    if spec.status == "blocked":
        raise ValueError(
            f"spec {slug!r} is blocked by deterministic checks "
            f"(lint: {len(spec.lint_issues)}); fix and regenerate before approving"
        )
    spec.status = "approved"
    # Pin what this approval covered (§13.35.5). Editing the spec afterwards
    # is legal — it just stops being approved until an SCR ratifies it.
    spec.approved_hash = contract_hash(spec)
    _save(repo_dir, spec)
    return spec
