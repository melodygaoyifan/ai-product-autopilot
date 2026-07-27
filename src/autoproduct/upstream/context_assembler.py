"""The Context Manifest (§13.25.2, §13.29.3, §13.35.5).

Three mechanisms the docs treat as one, because they only work together:

1. **Assembly.** A task's context is collected deterministically under a
   token cap — spec slice first, code neighborhoods last — and every entry
   carries the SHA-256 of what was read.
2. **Grounding receipts.** A writer reports `sources_read`; the harness
   checks it against the manifest. A writer that produced a spec without
   reading the module specs listed for it is a *contract violation*
   (§11.18.3), not a quality note. This is the methodology reference's
   requiredSources / sourcesRead / missingSources protocol, mechanized.
3. **Drift detection (§35.5).** Re-hashing the manifest before use catches
   a human editing a frozen artifact mid-flight. The response is to block
   the task with "spec changed outside SCR" and let a retro-SCR ratify or
   revert — *the system refuses to proceed on an unratified fork; it does
   not fight the human.*

One deliberate refusal: when a task's REQUIRED context does not fit the
cap, that is a planning defect, not a compression challenge. Assembly
returns `TASK_BLOCKED_CONTEXT_OVERFLOW` with a split proposal for Planning
rather than quietly dropping the spec slice a writer needs to be correct.
"""

from __future__ import annotations

import hashlib
import pathlib
from typing import Literal

from pydantic import BaseModel, Field

# Tokens are estimated, never counted by a tokenizer: the cap exists to
# bound assembly, and a deterministic 4-chars-per-token heuristic keeps the
# manifest reproducible across provider tokenizers. Documented rather than
# hidden, because it is why the cap is a soft bound in practice.
CHARS_PER_TOKEN = 4
DEFAULT_CAP_TOKENS = 40_000

EntryKind = Literal[
    "spec", "design", "module_spec", "constraints", "scr", "test", "code",
]

# Ranking: the contract a writer must not reinterpret comes first, the code
# it may explore comes last (§13.29.3 "spec slice first, code last").
_RANK: dict[str, int] = {
    "spec": 0, "constraints": 1, "design": 2, "module_spec": 3,
    "scr": 4, "test": 5, "code": 6,
}
# Kinds a writer cannot be correct without. Everything else is optional and
# gets taken while it fits.
_REQUIRED_KINDS = {"spec", "constraints", "module_spec"}
# ...except artifacts that only RENDER a required one for humans. spec.md is
# spec.yaml formatted for a reader; demanding both would make the machine
# contract look like two obligations and fire a violation over a heading.
_DERIVED_VIEWS = {"spec.md"}
_CODE_SUFFIXES = (".py", ".js", ".ts", ".tsx", ".wxml", ".java", ".cs", ".go")


class ContextOverflow(Exception):
    """Required context exceeds the cap — a planning defect (§13.29.3)."""

    code = "TASK_BLOCKED_CONTEXT_OVERFLOW"

    def __init__(self, message: str, split_proposal: list[str]):
        super().__init__(message)
        self.split_proposal = split_proposal


class ContextDrift(Exception):
    """A manifest entry changed since assembly (§13.35.5). Retro-SCR
    ratifies or reverts; the run does not proceed on an unratified fork."""

    code = "SPEC_CHANGED_OUTSIDE_SCR"

    def __init__(self, message: str, drifted: list[str]):
        super().__init__(message)
        self.drifted = drifted


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ManifestEntry(BaseModel):
    path: str  # repo-relative
    kind: EntryKind
    required: bool
    content_hash: str
    tokens: int
    probe: str = Field(
        default="",
        description="distinctive text from this entry whose presence in a "
        "writer's prompt proves the entry reached it — the receipt mechanism "
        "for pushed context (see grounding_receipts)",
    )


class ContextManifest(BaseModel):
    task_id: str
    cap_tokens: int
    entries: list[ManifestEntry] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)  # optional, did not fit

    @property
    def required(self) -> list[ManifestEntry]:
        return [e for e in self.entries if e.required]

    @property
    def optional(self) -> list[ManifestEntry]:
        return [e for e in self.entries if not e.required]

    @property
    def tokens(self) -> int:
        return sum(e.tokens for e in self.entries)

    def entry(self, path: str) -> ManifestEntry | None:
        return next((e for e in self.entries if e.path == path), None)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


PROBE_CHARS = 80


def normalize(text: str) -> str:
    """Collapse all whitespace. Both sides of a grounding probe are
    normalized, so a line re-wrapped by a YAML dump still matches the same
    line read from disk — the content reached the writer either way."""
    return " ".join((text or "").split())


def make_probe(text: str) -> str:
    """The most distinctive line in an artifact.

    The longest line is a good proxy: in a spec it is an acceptance
    criterion, in CLAUDE.md a constraint, in a module spec an invariant —
    exactly the content whose absence from a prompt would matter. Short
    files fall back to their whole normalized text.
    """
    lines = [normalize(line) for line in (text or "").splitlines()]
    meaningful = [line for line in lines if len(line) >= 20]
    if not meaningful:
        return normalize(text)[:PROBE_CHARS]
    return max(meaningful, key=len)[:PROBE_CHARS]


def _candidate(
    root: pathlib.Path, path: pathlib.Path, kind: EntryKind,
    required_kinds: set[str] | None = None,
):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    kinds = required_kinds if required_kinds is not None else _REQUIRED_KINDS
    required = kind in kinds and path.name not in _DERIVED_VIEWS
    return ManifestEntry(
        path=str(path.relative_to(root)),
        kind=kind,
        required=required,
        content_hash=content_hash(text),
        tokens=estimate_tokens(text),
        probe=make_probe(text),
    )


def collect_candidates(
    repo_dir: str | pathlib.Path, slug: str, *,
    files_expected: list[str] | None = None,
    required_kinds: set[str] | None = None,
) -> list[ManifestEntry]:
    """Everything this task could legitimately need, unranked."""
    root = pathlib.Path(repo_dir).resolve()
    found: list[ManifestEntry] = []

    def add(path: pathlib.Path, kind: EntryKind) -> None:
        if path.is_file():
            entry = _candidate(root, path, kind, required_kinds)
            if entry is not None and not any(e.path == entry.path for e in found):
                found.append(entry)

    spec_dir = root / "specs" / slug
    add(spec_dir / "spec.yaml", "spec")
    add(spec_dir / "spec.md", "spec")
    add(root / "CLAUDE.md", "constraints")
    add(root / "product" / "design.md", "design")
    for module_spec in sorted((root / ".mas" / "specs").glob("*.spec.yaml")):
        add(module_spec, "module_spec")
    for scr in sorted((root / ".mas" / "scr").glob("SCR-*.yaml")):
        add(scr, "scr")
    for skeleton in sorted((root / "tests").glob("test_*.py")):
        add(skeleton, "test")
    # Code neighborhoods from the task's declared globs — last by rank, and
    # only what the plan said this task would touch.
    for glob in files_expected or []:
        for path in sorted(root.glob(glob)):
            if path.is_file() and path.suffix in _CODE_SUFFIXES:
                add(path, "code")
    return found


def assemble(
    repo_dir: str | pathlib.Path,
    slug: str,
    *,
    task_id: str | None = None,
    files_expected: list[str] | None = None,
    cap_tokens: int = DEFAULT_CAP_TOKENS,
    required_kinds: set[str] | None = None,
) -> ContextManifest:
    """Build the manifest, or refuse (ContextOverflow) when required context
    does not fit — never by silently dropping the contract.

    `required_kinds` overrides what counts as required. The SPEC stage needs
    this: the spec is what it is about to write, so it cannot be required
    reading — but the constraints and module invariants it must not violate
    still are.
    """
    candidates = collect_candidates(
        repo_dir, slug, files_expected=files_expected,
        required_kinds=required_kinds,
    )
    ranked = sorted(candidates, key=lambda e: (_RANK[e.kind], e.path))
    required = [e for e in ranked if e.required]
    optional = [e for e in ranked if not e.required]

    required_tokens = sum(e.tokens for e in required)
    if required_tokens > cap_tokens:
        biggest = sorted(required, key=lambda e: -e.tokens)[:3]
        raise ContextOverflow(
            f"task {task_id or slug!r}: required context is ~{required_tokens} "
            f"tokens against a {cap_tokens} cap — split the task rather than "
            "compressing the contract",
            [f"{e.path} (~{e.tokens} tokens)" for e in biggest],
        )

    kept = list(required)
    budget = cap_tokens - required_tokens
    dropped: list[str] = []
    for entry in optional:
        if entry.tokens <= budget:
            kept.append(entry)
            budget -= entry.tokens
        else:
            dropped.append(entry.path)
    return ContextManifest(
        task_id=task_id or slug, cap_tokens=cap_tokens,
        entries=kept, dropped=dropped,
    )


def check_drift(
    manifest: ContextManifest, repo_dir: str | pathlib.Path
) -> list[str]:
    """Paths whose content changed (or vanished) since assembly. §35.5's
    detector: a human edit mid-flight is found here, not after the build."""
    root = pathlib.Path(repo_dir).resolve()
    drifted = []
    for entry in manifest.entries:
        path = root / entry.path
        if not path.is_file():
            drifted.append(f"{entry.path} (removed)")
            continue
        try:
            current = content_hash(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            drifted.append(f"{entry.path} (unreadable)")
            continue
        if current != entry.content_hash:
            drifted.append(entry.path)
    return drifted


def require_no_drift(
    manifest: ContextManifest, repo_dir: str | pathlib.Path
) -> None:
    """Raise ContextDrift when the bundle moved under the run."""
    drifted = check_drift(manifest, repo_dir)
    if drifted:
        raise ContextDrift(
            "spec changed outside SCR: "
            + ", ".join(drifted[:5])
            + " — a retro-SCR must ratify or revert this edit before the task "
            "proceeds (the system does not proceed on an unratified fork)",
            drifted,
        )


class GroundingViolation(BaseModel):
    rule: str  # unread_required | hash_mismatch | unknown_source
    path: str
    detail: str


def verify_sources_read(
    manifest: ContextManifest, sources_read: dict[str, str]
) -> list[GroundingViolation]:
    """Check a writer's receipts against the manifest (§13.25.2).

    Three ways to fail, all contract violations rather than quality notes:
    a required entry never read, an entry read at a different hash than the
    manifest recorded, or a claimed read of something not in the manifest.
    """
    violations: list[GroundingViolation] = []
    for entry in manifest.required:
        if entry.path not in sources_read:
            violations.append(GroundingViolation(
                rule="unread_required", path=entry.path,
                detail="required context was never read by the writer",
            ))
        elif sources_read[entry.path] != entry.content_hash:
            violations.append(GroundingViolation(
                rule="hash_mismatch", path=entry.path,
                detail="read a different version than the manifest recorded",
            ))
    for path, digest in sources_read.items():
        entry = manifest.entry(path)
        if entry is None:
            violations.append(GroundingViolation(
                rule="unknown_source", path=path,
                detail="writer read something the manifest does not list",
            ))
        elif not entry.required and digest != entry.content_hash:
            violations.append(GroundingViolation(
                rule="hash_mismatch", path=path,
                detail="read a different version than the manifest recorded",
            ))
    return violations


def grounding_receipts(
    manifest: ContextManifest, prompt_text: str
) -> dict[str, str]:
    """Receipts derived from what a prompt ACTUALLY contains.

    The doc's `ArtifactWriter` has read_file tools and reports its own
    `sources_read`. Our writers get context *pushed* into the prompt
    instead, so a self-reported receipt would be the model's word about its
    own attention. The mechanized equivalent for pushed context is to look:
    an entry whose probe appears in the prompt demonstrably reached the
    writer, and one whose probe is absent demonstrably did not.

    This checks **assembly**, not attention — it cannot prove the model read
    what it was handed. What it does catch is the real and recurring bug:
    a prompt built without the module-spec invariants the artifact will be
    judged against.
    """
    haystack = normalize(prompt_text)
    receipts: dict[str, str] = {}
    for entry in manifest.entries:
        probe = normalize(entry.probe)
        if probe and probe in haystack:
            receipts[entry.path] = entry.content_hash
    return receipts


def verify_prompt_grounding(
    manifest: ContextManifest, prompt_text: str
) -> list[GroundingViolation]:
    """Required entries whose content never made it into the prompt."""
    return verify_sources_read(manifest, grounding_receipts(manifest, prompt_text))


def persist_manifest(
    manifest: ContextManifest, repo_dir: str | pathlib.Path, slug: str
) -> pathlib.Path:
    """Record the manifest beside the run for forensics (§13.35)."""
    import yaml

    path = pathlib.Path(repo_dir) / ".mas" / "manifests" / f"{slug}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(manifest.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def render_manifest(
    manifest: ContextManifest, repo_dir: str | pathlib.Path
) -> tuple[str, dict[str, str]]:
    """The writer's context block, plus the `sources_read` receipts it would
    report. Returned together so the caller can verify the receipts against
    the manifest without trusting the model to report them."""
    root = pathlib.Path(repo_dir).resolve()
    blocks = []
    receipts: dict[str, str] = {}
    for entry in manifest.entries:
        path = root / entry.path
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        receipts[entry.path] = content_hash(text)
        blocks.append(
            f'<context path="{entry.path}" kind="{entry.kind}" '
            f'required="{str(entry.required).lower()}">\n{text}\n</context>'
        )
    return "\n\n".join(blocks), receipts
