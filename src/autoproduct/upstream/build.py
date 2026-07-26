"""Coding stage (§13, ADR-U01) — single-writer implementer, test-first.

Deliberately NOT a voting stage: generation is single-writer; judgment
lives in the review stage the diff is handed to afterwards. The build
gate is deterministic — the spec's test skeletons (and everything else in
the suite) must pass before the commit exists.

Bounds: ≤12 files, ≤500 lines each, repo-relative paths only, never
.git/.mas/specs. ≤3 implement-run-fix iterations, then BUILD_FAILED.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from autoproduct.providers import get_provider
from autoproduct.testing import (
    _pytest_in_docker,
    _pytest_in_subprocess,
    _run,
    docker_available,
)
from autoproduct.upstream.spec import Spec, load_spec
from autoproduct.upstream.workspace import load_project
from autoproduct.yamlx import extract_mapping

IMPLEMENTER_MARKER = "single-writer implementer in a greenfield product system"

MAX_ITERATIONS = 3
_MAX_FILES = 12
_MAX_FILE_LINES = 500
_FORBIDDEN_PREFIXES = (".git", ".mas", "specs")


class BuildResult(BaseModel):
    slug: str
    status: str  # built | build_failed | error
    iterations: int = 0
    files_written: list[str] = Field(default_factory=list)
    modified_existing: list[str] = Field(
        default_factory=list, description="scope_check-lite: pre-existing files "
        "the implementer changed — visible, reviewed, never silent"
    )
    wireup_issues: list[str] = Field(default_factory=list)
    test_summary: str = ""
    commit: str | None = None
    detail: str = ""


_SYSTEM = f"""You are the {IMPLEMENTER_MARKER}. Implement the approved spec
below, test-first: the test skeletons are the contract — write them as real
tests that encode the EARS criteria, then the smallest implementation that
passes them.

Rules:
- Return COMPLETE file contents (no diffs). At most {_MAX_FILES} files,
  each under {_MAX_FILE_LINES} lines. Include the test files.
- Respect the project constraints; no new dependencies unless the spec's
  design names them.
- Where a <source_contract> is provided, it is the founder's LITERAL
  interface contract: use its exact paths, methods, field names, and
  enumerated values verbatim (a field the contract calls "item" is never
  "index"). The acceptance probes are written from that contract, not
  from your code — inventing a synonym fails them all.
- Endpoints never crash on user input: invalid JSON, wrong types, missing
  or unknown fields get an explicit 4xx error response whose JSON body
  carries a human-readable message (an "error" field unless the contract
  fixes another shape — an empty {{}} body fails the founder's checks).
  An unhandled exception on malformed input is a defect, not a shortcut.
- tests/conftest.py and tests/helpers*.py are a SHARED vocabulary that
  other tasks' committed tests import. Reuse the existing fixtures and
  helpers as-is; extend them only additively (a rewrite that drops or
  renames an existing name is discarded). Never build a parallel fixture
  set for the same job.
- If the existing product already satisfies every criterion, do NOT
  rewrite source files: submit ONLY your skeleton test files proving the
  criteria — a passing tests-only submission closes the task as built.
- Never touch paths under {_FORBIDDEN_PREFIXES}.

Respond with ONLY YAML:
files:
  - path: ...
    new_content: |
      ...
notes: one line
"""


def _run_tests(repo: Path):
    return (
        _pytest_in_docker(repo) if docker_available() else _pytest_in_subprocess(repo)
    )


_BOOT_GATE_TIMEOUT_S = 15
_BOOT_CONTRACT_HINT = (
    "the entry point must start its own server on the PORT env var when run "
    "directly; for FastAPI append: if __name__ == \"__main__\": import uvicorn; "
    "uvicorn.run(app, host=\"127.0.0.1\", port=int(os.environ.get(\"PORT\", \"8000\")))"
)


def _boot_gate(repo: Path) -> str | None:
    """Web-profile extension of Gate U4: the product must SERVE, not just
    pass its suite — the founder and every probe boot it as
    `python <entry>` with $PORT set (product-bench run 4: every built web
    task failed all probes on 'server never listened' because nothing
    enforced this contract). Returns feedback text on failure; None when
    the entry listens or when there is no entry point yet to boot."""
    import os
    import socket
    import sys

    entry = next(
        (e for e in ("app/main.py", "main.py", "app.py") if (repo / e).exists()), None
    )
    if entry is None:
        return None
    with socket.socket() as picker:
        picker.bind(("127.0.0.1", 0))
        port = picker.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, entry],
        cwd=repo,
        env={**os.environ, "PORT": str(port), "PYTHONPATH": str(repo)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + _BOOT_GATE_TIMEOUT_S
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                err = (proc.stderr.read() or b"").decode(errors="replace")[-400:]
                return (
                    f"BOOT GATE: `python {entry}` exited with rc={proc.returncode} "
                    f"instead of serving. stderr tail: {err.strip() or '(empty)'} — "
                    + _BOOT_CONTRACT_HINT
                )
            try:
                socket.create_connection(("127.0.0.1", port), 0.5).close()
                return None
            except OSError:
                time.sleep(0.3)
        return (
            f"BOOT GATE: `python {entry}` ran {_BOOT_GATE_TIMEOUT_S}s without "
            "listening on 127.0.0.1:$PORT — " + _BOOT_CONTRACT_HINT
        )
    finally:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass


def _preserve_failed_attempt(repo: Path, slug: str, source: Path | None = None) -> str:
    """Failure forensics that survives cleanup: copy the dirty tree to
    .mas/failed-builds/<slug>. Before this, 'worktree left for inspection'
    was untrue — worktrees are force-removed, and the run-4 postmortem had
    to reconstruct failed attempts from workspace residue."""
    import shutil

    keep = repo / ".mas" / "failed-builds" / slug
    shutil.rmtree(keep, ignore_errors=True)
    keep.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source or repo,
        keep,
        ignore=shutil.ignore_patterns(
            ".git", ".mas", ".venv", "node_modules", "__pycache__", ".pytest_cache"
        ),
    )
    return str(keep.relative_to(repo))


def _reset_workspace(repo: Path, pre_existing: set[str]) -> None:
    """In-place build failed: drop every file the attempt created and
    restore tracked modifications. Uncommitted residue otherwise leaks into
    sibling tasks, later stages, and the probes (run 4 left 724 inserted
    lines dirtying the case-03 workspace the probes then measured)."""
    for path in sorted(repo.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if ".git" in path.parts or ".mas" in path.parts:
            continue
        if path.is_file():
            if str(path.relative_to(repo)) not in pre_existing:
                path.unlink(missing_ok=True)
        else:
            try:
                path.rmdir()  # only succeeds once emptied — intended
            except OSError:
                pass
    subprocess.run(
        ["git", "checkout", "--", "."], cwd=repo, capture_output=True, timeout=60
    )


def _removed_names(old: str, new: str) -> set[str]:
    """Top-level names a rewrite dropped. Support modules under tests/
    are a shared vocabulary — sibling tasks' committed tests import these
    names, so removal breaks their collection (run 7, case 04: a conftest
    rewrite lost post_json/create_candidate and every iteration died on
    ImportError). Unparseable code returns empty — the suite gate judges it."""
    old_names, new_names = _toplevel_names(old), _toplevel_names(new)
    if old_names is None or new_names is None:
        return set()
    # Privates are not vocabulary: nothing outside the module should import
    # a _name, and guarding them blocks legitimate internal restructuring
    # (run 8, case 01 t3: a helpers rewrite adding the public name its tests
    # needed was droppable purely over reshuffled _check_url/_do).
    return {n for n in (old_names - new_names) if not n.startswith("_")}


def _toplevel_names(src: str) -> set[str] | None:
    import ast

    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    return {
        n.name for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    } | {
        t.id for n in tree.body if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name)
    }


def _stale_import_note(repo: Path) -> str:
    """Cross-iteration drift detector. Files persist between build
    iterations, so a vocabulary change mid-build leaves earlier files
    importing names that never existed — collection dies before any test
    runs (run 8, case 01 t3: half the tests imported http_post, half
    post). A deterministic scan names the exact files and the available
    names; returns '' when clean."""
    import ast

    problems: list[str] = []
    seen: set[Path] = set()
    for path in sorted(set(repo.glob("tests/**/*.py")) | set(repo.glob("tests/*.py"))):
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
                continue
            if not (node.module.startswith("tests") or node.module in ("conftest", "helpers")):
                continue
            target = repo / (node.module.replace(".", "/") + ".py")
            if not target.is_file():
                continue
            available = _toplevel_names(
                target.read_text(encoding="utf-8", errors="replace")
            )
            if available is None:
                continue
            for alias in node.names:
                if alias.name != "*" and alias.name not in available:
                    public = ", ".join(sorted(n for n in available if not n.startswith("_"))[:8])
                    problems.append(
                        f"- {path.relative_to(repo)}: `from {node.module} import "
                        f"{alias.name}` — {target.relative_to(repo)} defines: {public or '(nothing public)'}"
                    )
    if not problems:
        return ""
    return (
        "STALE IMPORTS — these files (yours, possibly from an earlier "
        "iteration; files persist between iterations) import names that do "
        "not exist:\n" + "\n".join(problems[:5]) + "\n"
        "Resubmit those files to use the existing names, or add the missing "
        "names additively to the module they import from."
    )


def _write_files(
    repo: Path, files: list[dict], *, allowed_test_paths: set[str] | None = None
) -> tuple[list[str], list[str]]:
    """Two-pass: validate EVERY file first, then write — a refusal never
    leaves partial state behind. Returns (written, kept) where kept are
    skeleton files the implementer tried to weaken: the on-disk skeleton
    WINS silently-but-visibly instead of failing the batch — real models
    reword their own skeleton tests every attempt (bench run 3, 5/8 tasks
    dead on this wall), and a refusal loop never converges."""
    validated: list[tuple[str, str]] = []
    kept: list[str] = []
    for f in files[:_MAX_FILES]:
        # A malformed entry must surface as ValueError — the build loop's
        # feedback channel — not KeyError, which escapes it and kills the
        # whole run (product-bench run 4, case 01: one entry without
        # new_content zeroed the case).
        if not isinstance(f, dict) or not f.get("path") or "new_content" not in f:
            raise ValueError(
                "malformed file entry (every entry needs 'path' and COMPLETE "
                f"'new_content'): {str(f)[:120]!r}"
            )
        rel = str(f["path"]).lstrip("/")
        if any(rel.startswith(p) for p in _FORBIDDEN_PREFIXES) or ".." in rel:
            raise ValueError(f"implementer touched forbidden path {rel!r}")
        # §13.29.5 write-lock: existing non-skeleton TEST files are
        # read-only to the implementer. A blocking test is either its bug
        # or a spec gap — never a test to edit. (Reward-hacking defense,
        # structural.) Support modules under tests/ (helpers, conftest,
        # __init__) are NOT walled — feature tasks legitimately extend
        # shared fixtures (run 3: t3 died here) — but they pass through
        # the same weakening guard below, so gutting a helper's asserts
        # still gets the file dropped, and sabotaged fixtures fail the
        # other specs' tests in the suite gate.
        is_test = rel.startswith("tests/") or Path(rel).name.startswith("test_")
        if (
            Path(rel).name.startswith("test_")
            and (repo / rel).exists()
            and allowed_test_paths is not None
            and rel not in allowed_test_paths
        ):
            raise ValueError(
                f"implementer tried to modify existing test {rel!r} — existing "
                "tests are read-only (fix the code, or the spec is wrong)"
            )
        content = str(f["new_content"])
        if is_test and (repo / rel).exists():
            # Its own skeleton surface is rewritable, but never WEAKENABLE:
            # assertion_delta rejects removed asserts / added skips citing
            # the exact node (§13.29.5). The rejection drops THIS file only —
            # the skeleton stays the wall; the rest of the batch proceeds.
            from autoproduct.tools.integrity import assertion_delta

            weakened = assertion_delta(
                (repo / rel).read_text(encoding="utf-8", errors="replace"), content
            )
            if weakened:
                kept.append(
                    f"{rel} (skeleton kept — your version dropped: "
                    + "; ".join(f"{c.change}: {c.node[:80]}" for c in weakened[:3])
                    + ")"
                )
                continue
            if not Path(rel).name.startswith("test_"):
                # conftest/helpers are additive-only: dropped names break
                # sibling tasks' imports.
                lost = _removed_names(
                    (repo / rel).read_text(encoding="utf-8", errors="replace"),
                    content,
                )
                if lost:
                    kept.append(
                        f"{rel} (existing version kept — your rewrite removed "
                        f"names committed tests import: {', '.join(sorted(lost)[:6])}. "
                        "Extend this file additively; never rename or drop.)"
                    )
                    continue
        if len(content.splitlines()) > _MAX_FILE_LINES:
            raise ValueError(f"{rel} exceeds {_MAX_FILE_LINES} lines")
        validated.append((rel, content))

    written = []
    for rel, content in validated:
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(rel)
    return written, kept


def _append_design_memory(repo: Path, spec: Spec, files: list[str]) -> None:
    """product/design.md — the evolving architecture the Spec stage reads
    back, so feature N+1 extends the design instead of re-deriving it."""
    path = repo / "product" / "design.md"
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        path.write_text("# Architecture (evolving — appended per build)\n", encoding="utf-8")
    entry = (
        f"\n## {spec.title} ({spec.slug})\n\n{spec.design.strip()}\n\n"
        f"files: {', '.join(f for f in files if not f.startswith('tests/'))}\n"
    )
    path.write_text(path.read_text(encoding="utf-8") + entry, encoding="utf-8")


def _write_changelog_fragment(repo: Path, spec: Spec, files: list[str]) -> None:
    directory = repo / "product" / "changelog"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{spec.slug}.md").write_text(
        f"**{spec.title}** — {len(spec.criteria)} acceptance criteria, "
        f"{len(files)} file(s). User-visible: {spec.criteria[0] if spec.criteria else spec.title}\n",
        encoding="utf-8",
    )


def _file_tree(repo: Path, cap: int = 200) -> str:
    lines = []
    for path in sorted(repo.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo)
        if any(part in (".git", ".mas", "__pycache__", "node_modules", ".venv") for part in rel.parts):
            continue
        lines.append(str(rel))
        if len(lines) >= cap:
            lines.append("… (truncated)")
            break
    return "\n".join(lines)


def _related_sources(repo: Path, spec: Spec, cap_files: int = 6, cap_lines: int = 200) -> str:
    """Existing files the spec's design mentions — the implementer extends
    the product, it does not recreate it (feature-FDR awareness)."""
    mentioned = re.findall(r"[\w/]+\.(?:py|js|ts|wxml|wxss|json|html)", spec.design)
    blocks = []
    for rel in dict.fromkeys(mentioned):
        path = repo / rel
        if path.is_file():
            text = "\n".join(
                path.read_text(encoding="utf-8", errors="replace").splitlines()[:cap_lines]
            )
            blocks.append(f'<existing_file path="{rel}">\n{text}\n</existing_file>')
        if len(blocks) >= cap_files:
            break
    return "\n\n".join(blocks)


def data_gate_blockers(repo: Path, profile: str) -> list[str]:
    """§18.48.1: the data profile's build gate also runs the workspace's
    declared/detected external checks (dbt, contracts, DAG imports).
    findings/error block the commit; `skipped` (tool not installed, nothing
    configured) is visible in the check output but does not block —
    availability-gating, not silent absence."""
    if profile != "data":
        return []
    from autoproduct.adoption.data_tools import run_data_checks

    return [
        f"{r.slot} ({r.detail})"
        for r in run_data_checks(repo)
        if r.status in ("findings", "error")
    ]


def finalize_build_bookkeeping(repo_dir: str | Path, slug: str, files: list[str]) -> None:
    """Post-build records: spec frozen, design memory, changelog, actuals.
    Split out so parallel worktree builds can run it after their merge."""
    repo = Path(repo_dir).resolve()
    spec = load_spec(repo, slug)
    spec.built = True
    from autoproduct.upstream.spec import _save as _save_spec

    _save_spec(repo, spec)
    _append_design_memory(repo, spec, files)
    _write_changelog_fragment(repo, spec, files)


def run_build(
    repo_dir: str | Path,
    slug: str,
    *,
    provider: str = "anthropic",
    model: str = "claude-opus-4-8",
    in_branch: bool = False,
    task_lane: str = "core",
    task_estimate_hours: float = 0.0,
    source_contract: str = "",
) -> BuildResult:
    """in_branch=True: build in an isolated worktree on branch
    build/<slug> (parallel-lane mode) — the caller merges and then calls
    finalize_build_bookkeeping. Default: build in place, all-inclusive."""
    started = time.monotonic()
    repo = Path(repo_dir).resolve()
    if in_branch:
        import tempfile

        worktree = Path(tempfile.mkdtemp(prefix=f"autoproduct-lane-{slug[:16]}-"))
        added = _run(
            ["git", "worktree", "add", "-B", f"build/{slug}", str(worktree), "HEAD"], repo
        )
        if added.returncode != 0:
            return BuildResult(slug=slug, status="error", detail=added.stderr[:300])
        # .mas/ is gitignored config, not history — the lane worktree needs
        # the project + services config to build.
        (worktree / ".mas").mkdir(exist_ok=True)
        for config in ("project.yaml", "services.yaml"):
            source = repo / ".mas" / config
            if source.exists():
                (worktree / ".mas" / config).write_text(
                    source.read_text(encoding="utf-8"), encoding="utf-8"
                )
        result: BuildResult | None = None
        try:
            result = _run_build_inner(
                worktree, slug, provider=provider, model=model, started=started,
                bookkeeping=False, task_lane=task_lane,
                task_estimate_hours=task_estimate_hours,
                source_contract=source_contract,
            )
            result.detail = (result.detail + " " if result.detail else "") + f"branch build/{slug}"
            return result
        finally:
            import shutil as _shutil

            if result is not None and result.status != "built":
                preserved = _preserve_failed_attempt(repo, slug, source=worktree)
                result.detail = (
                    (result.detail + " " if result.detail else "")
                    + f"(failed attempt preserved at {preserved})"
                )
            _run(["git", "worktree", "remove", "--force", str(worktree)], repo)
            _shutil.rmtree(worktree, ignore_errors=True)
    return _run_build_inner(
        repo, slug, provider=provider, model=model, started=started,
        bookkeeping=True, task_lane=task_lane,
        task_estimate_hours=task_estimate_hours,
        source_contract=source_contract,
    )


def _run_build_inner(
    repo: Path,
    slug: str,
    *,
    provider: str,
    model: str,
    started: float,
    bookkeeping: bool,
    task_lane: str = "core",
    task_estimate_hours: float = 0.0,
    source_contract: str = "",
) -> BuildResult:
    project = load_project(repo)
    if not source_contract:
        # Same fallback as the spec stage: the workspace FDR is the
        # founder's literal contract. The live post-fix test showed drift
        # migrating to the implementer once specs held (scores handler
        # invented "index" for the FDR's "item" — every probe died on it).
        fdr_file = repo / "FDR.md"
        if fdr_file.exists():
            source_contract = fdr_file.read_text(encoding="utf-8")
    spec: Spec = load_spec(repo, slug)
    if spec.status != "approved":
        return BuildResult(
            slug=slug,
            status="error",
            detail=f"spec status is {spec.status!r} — Gate U3 requires "
            f"`autoproduct spec-approve {slug}` first",
        )

    provider_impl = get_provider(provider)
    claude_md = repo / "CLAUDE.md"
    constraints = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
    existing = _related_sources(repo, spec)
    fixture_blocks = []
    for rel in ["conftest.py", "tests/conftest.py"] + sorted(
        str(q.relative_to(repo)) for q in repo.glob("tests/helpers*.py")
    ):
        path = repo / rel
        if path.is_file():
            body = "\n".join(
                path.read_text(encoding="utf-8", errors="replace").splitlines()[:200]
            )
            fixture_blocks.append(f'<existing_file path="{rel}">\n{body}\n</existing_file>')
    if fixture_blocks:
        # The vocabulary saga's root cause: _related_sources only surfaces
        # files the spec's design text happens to mention, so implementers
        # never saw the committed fixtures and re-invented them blindly
        # (http/http_post/base_url across runs 7-9). Always show them.
        existing = (existing + "\n\n" if existing else "") + (
            '<shared_test_fixtures note="these already exist — USE these '
            'fixture and helper names in your tests; extend additively, '
            'never re-invent">\n' + "\n\n".join(fixture_blocks)
            + "\n</shared_test_fixtures>"
        )
    from autoproduct.upstream.blocks import blocks_context
    from autoproduct.upstream.provisioning import services_context

    services = services_context(repo)
    blocks = blocks_context(
        project.profile, f"{spec.title} {spec.design} {' '.join(spec.criteria)}"
    )
    if blocks:
        existing = (existing + "\n\n" if existing else "") + blocks
    base_user = (
        f"<constraints>\n{constraints}\n</constraints>\n\n"
        + (f"<services>\n{services}\n</services>\n\n" if services else "")
        + f"<repo_tree>\n{_file_tree(repo)}\n</repo_tree>\n\n"
        + (f"{existing}\n\n" if existing else "")
        + "You are EXTENDING the existing product above — integrate with it, "
        "never recreate it. Existing test files are read-only to you. Your "
        "spec's skeleton tests already exist ON DISK: do not resubmit them "
        "(a version missing any existing assert is silently discarded and "
        "the skeleton kept) — write the SOURCE files that make them pass, "
        "plus any NEW test files.\n\n"
        + (f"<source_contract>\n{source_contract[:3000]}\n</source_contract>\n\n"
           if source_contract.strip() else "")
        + f"<spec>\n{yaml.safe_dump(spec.model_dump(include={'title', 'design', 'criteria'}), sort_keys=False, allow_unicode=True)}"
        f"test_skeletons:\n"
        + "\n".join(f"- {s.path}: {s.purpose} (covers {s.covers})" for s in spec.test_skeletons)
        + "\n</spec>"
    )
    allowed_tests = {s.path for s in spec.test_skeletons}
    pre_existing = {
        str(p.relative_to(repo))
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.parts and ".mas" not in p.parts
    }

    feedback = ""
    written: list[str] = []
    report = None
    for iteration in range(1, MAX_ITERATIONS + 1):
        raw = provider_impl.complete(
            model=model,
            system=_SYSTEM,
            user=base_user
            + (f"\n\n<test_failure>\n{feedback}\n</test_failure>" if feedback else ""),
            max_tokens=16384,
        )
        try:
            data = extract_mapping(raw, ("files",))
            written, kept = _write_files(
                repo, data.get("files") or [], allowed_test_paths=allowed_tests
            )
        except ValueError as exc:
            # A refused write (read-only test, weakened assert, unparseable
            # output) is FEEDBACK, not a fatal error — real implementers
            # routinely re-emit existing test files, and the instant-error
            # version collapsed both real bench cases to 1/7 tasks built.
            # Structural walls stay: nothing was written; the model gets
            # the wall's text and a bounded retry.
            if iteration == MAX_ITERATIONS:
                detail = str(exc)
                if bookkeeping and written:
                    # Earlier iterations already wrote into the shared
                    # workspace — same residue rule as the failure returns.
                    preserved = _preserve_failed_attempt(repo, slug)
                    _reset_workspace(repo, pre_existing)
                    detail += f" (failed attempt preserved at {preserved}; workspace reset)"
                return BuildResult(slug=slug, status="error", iterations=iteration, detail=detail)
            feedback = (
                f"WRITE REFUSED: {exc}. Resubmit ALL your files WITHOUT the "
                "refused change — existing tests are read-only walls, not "
                "suggestions."
            )
            continue
        if not written:
            if iteration == MAX_ITERATIONS:
                detail = "implementer returned no files"
                if bookkeeping:
                    preserved = _preserve_failed_attempt(repo, slug)
                    _reset_workspace(repo, pre_existing)
                    detail += f" (failed attempt preserved at {preserved}; workspace reset)"
                return BuildResult(
                    slug=slug, status="error", iterations=iteration,
                    detail=detail,
                )
            feedback = (
                "every file you returned was a weakened skeleton test and was "
                "discarded: " + "; ".join(kept) + ". Return the SOURCE files."
                if kept
                else "you returned no files; return the complete file set"
            )
            continue
        from autoproduct.testing import combine_reports, run_js_tests

        report = combine_reports(_run_tests(repo), run_js_tests(repo))
        python_skeletons = any(s.path.endswith(".py") for s in spec.test_skeletons)
        if report.status == "passed" or (
            report.status in ("no_tests", "skipped") and not python_skeletons
        ):
            # skipped = JS tests exist but no node runtime; the skip is
            # visible in the report and review still judges the diff.
            boot_failure = _boot_gate(repo) if project.profile == "web" else None
            if boot_failure is None:
                break
            feedback = boot_failure
            continue
        feedback = report.detail or report.summary
        stale = _stale_import_note(repo)
        if stale:
            feedback += "\n\n" + stale
        if kept:
            feedback += (
                "\n\nNOTE — these skeleton test files were NOT replaced (your "
                "version removed existing asserts; the on-disk skeleton wins): "
                + "; ".join(kept)
                + ". Make the CODE pass the skeleton as written."
            )
    else:
        detail = "build gate still failing after max iterations; nothing committed"
        if bookkeeping:
            # bookkeeping=True means we built IN the shared workspace (the
            # worktree path preserves + discards in the run_build wrapper).
            preserved = _preserve_failed_attempt(repo, slug)
            _reset_workspace(repo, pre_existing)
            detail += f" (failed attempt preserved at {preserved}; workspace reset)"
        return BuildResult(
            slug=slug,
            status="build_failed",
            iterations=MAX_ITERATIONS,
            files_written=written,
            test_summary=(feedback or report.summary) if report else feedback,
            detail=detail,
        )

    data_blockers = data_gate_blockers(repo, project.profile)
    if data_blockers:
        detail = "data checks failed: " + "; ".join(data_blockers) + " — nothing committed"
        if bookkeeping:
            preserved = _preserve_failed_attempt(repo, slug)
            _reset_workspace(repo, pre_existing)
            detail += f" (failed attempt preserved at {preserved}; workspace reset)"
        return BuildResult(
            slug=slug,
            status="build_failed",
            iterations=iteration,
            files_written=written,
            test_summary=report.summary if report else "",
            detail=detail,
        )

    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    committed = subprocess.run(
        ["git", "-c", "user.email=autoproduct@local", "-c", "user.name=autoproduct",
         "commit", "-qm",
         f"feat({slug}): {spec.title}\n\nImplements spec {slug} (Gate U4 build "
         f"gate passed: {report.summary}). Review with: autoproduct review HEAD~1"],
        cwd=repo, capture_output=True, text=True,
    )
    if committed.returncode != 0:
        return BuildResult(
            slug=slug, status="error", iterations=iteration,
            files_written=written, detail=committed.stderr[:300],
        )
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()

    if bookkeeping:
        finalize_build_bookkeeping(repo, slug, written)
    try:
        from autoproduct.upstream.plan import record_actual

        record_actual(
            repo, task_lane, task_estimate_hours or 1.0, time.monotonic() - started
        )
    except Exception:  # noqa: BLE001 — bookkeeping never fails a build
        pass

    from autoproduct.tools.wireup import wireup_check

    wireup = wireup_check(repo)
    return BuildResult(
        slug=slug,
        status="built",
        iterations=iteration,
        files_written=written,
        modified_existing=sorted(set(written) & pre_existing),
        wireup_issues=[f.title for f in wireup.findings][:10],
        test_summary=report.summary,
        commit=sha,
    )
