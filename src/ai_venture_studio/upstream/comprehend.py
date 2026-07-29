"""Repo comprehension (`avs map`) — read an existing codebase before touching it.

The gap this closes: nothing in the system could look at a codebase it had not
built. `blast_radius` matched FDR words against file *path strings* and never
read a byte of content; the feature planner saw a 200-path list; `.mas/deps.yaml`
and every `.mas/specs/*.spec.yaml` had to be hand-written, and
`arch_contract_check` — which compares imports against that hand-written graph —
had no production caller at all. "Understanding" was filename matching.

This module derives a map FROM the code: languages, entry points, modules with
their sizes, the import edges that actually exist, the HTTP surface, and where
the tests live. Everything here is a pure file read — no LLM, no subprocess, no
network — so it is cheap enough to run on every build and safe to render in a
page load.

Two deliberate limits, stated rather than hidden:

- Import edges are Python-only, reusing the same scanner the arch lane uses.
  Other languages get file/route inventory but no dependency graph.
- The derived graph describes what the code DOES, which is the honest starting
  point for brownfield adoption: today's reality becomes the baseline that must
  only shrink (arch.py's checkpoint pattern), never a claim that today's reality
  is the intended design.
"""

from __future__ import annotations

import pathlib
import re

import yaml
from pydantic import BaseModel, Field

# Same exclusions the voter tools use — vendored code is not this repo's shape.
_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".mas",
    ".pytest_cache", "dist", "build", ".next", ".idea", ".ruff_cache",
    "site-packages", "miniprogram_npm",
}
_LANG_BY_SUFFIX = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".go": "go",
    ".java": "java", ".cs": "csharp", ".rb": "ruby", ".rs": "rust",
    ".php": "php", ".wxml": "miniprogram", ".wxss": "miniprogram",
    ".vue": "vue", ".swift": "swift", ".kt": "kotlin",
}
_ENTRY_NAMES = (
    "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py", "server.py",
    "index.js", "server.js", "app.js", "main.go", "main.ts", "index.ts",
    "app.json",  # miniprogram
)
_TEST_HINTS = ("test_", "_test", "spec.", ".test.", ".spec.")

# `from x import y` / `import x` — the arch lane's pattern, reused so the map
# and the fitness function cannot disagree about what an import is.
_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))")


class ModuleFacts(BaseModel):
    """One top-level module or package, as it exists on disk."""

    name: str
    path: str
    files: int = 0
    lines: int = 0
    languages: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)  # observed module edges


class CodebaseMap(BaseModel):
    root: str
    languages: dict[str, int] = Field(default_factory=dict)  # language -> files
    total_files: int = 0
    total_lines: int = 0
    entry_points: list[str] = Field(default_factory=list)
    modules: list[ModuleFacts] = Field(default_factory=list)
    routes: list[str] = Field(default_factory=list)
    test_files: list[str] = Field(default_factory=list)
    package_root: str = ""
    notes: list[str] = Field(default_factory=list)

    @property
    def has_tests(self) -> bool:
        return bool(self.test_files)


def _iter_sources(root: pathlib.Path, cap: int = 20_000):
    seen = 0
    for path in sorted(root.rglob("*")):
        if seen >= cap:
            return
        if not path.is_file() or path.suffix not in _LANG_BY_SUFFIX:
            continue
        rel = path.relative_to(root)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        seen += 1
        yield rel, path


def _module_of(rel: pathlib.PurePath) -> str:
    """A file's owning module: its top directory, or "." at the repo root."""
    return rel.parts[0] if len(rel.parts) > 1 else "."


def comprehend_repo(repo_dir: str | pathlib.Path, *, cap: int = 20_000) -> CodebaseMap:
    """Derive the map from the code. Pure reads; safe to call anywhere."""
    root = pathlib.Path(repo_dir).resolve()
    result = CodebaseMap(root=str(root))
    by_module: dict[str, ModuleFacts] = {}
    py_files: dict[str, str] = {}

    for rel, path in _iter_sources(root, cap=cap):
        language = _LANG_BY_SUFFIX[path.suffix]
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        line_count = text.count("\n") + 1
        result.total_files += 1
        result.total_lines += line_count
        result.languages[language] = result.languages.get(language, 0) + 1

        name = str(rel)
        if any(hint in rel.name for hint in _TEST_HINTS) or "tests" in rel.parts:
            result.test_files.append(name)
        if rel.name in _ENTRY_NAMES:
            result.entry_points.append(name)
        if path.suffix == ".py":
            py_files[name] = text

        module_name = _module_of(rel)
        facts = by_module.setdefault(
            module_name,
            ModuleFacts(name=module_name,
                        path=module_name if module_name != "." else "."),
        )
        facts.files += 1
        facts.lines += line_count
        if language not in facts.languages:
            facts.languages.append(language)

    # Observed import edges, Python only (stated in the module docstring).
    known = set(by_module)
    for name, text in py_files.items():
        owner = _module_of(pathlib.PurePosixPath(name))
        facts = by_module.get(owner)
        if facts is None:
            continue
        for line in text.splitlines():
            match = _IMPORT.match(line)
            if not match:
                continue
            target = (match.group(1) or match.group(2) or "").split(".")[0]
            if (
                target
                and target != owner
                and target in known
                and target not in facts.imports
            ):
                facts.imports.append(target)

    result.modules = [by_module[k] for k in sorted(by_module)]
    for facts in result.modules:
        facts.imports.sort()

    # The HTTP surface, reusing the wireup scanner so the map and the
    # frontend/backend drift check agree on what a route is. collect_routes
    # yields path-SEGMENT tuples (its matcher compares shapes, so a path
    # parameter is a wildcard segment), which render back as paths here.
    from ai_venture_studio.tools.wireup import collect_routes

    result.routes = sorted(
        "/" + "/".join(str(part) for part in segments)
        for segments in collect_routes(root)
        if segments
    )

    # A package root only exists when one directory owns most of the code —
    # guessing one on a flat repo would make deps.yaml describe a fiction.
    code_modules = [
        m for m in result.modules
        if m.name not in (".",) and m.name not in ("tests", "test", "docs")
    ]
    if code_modules:
        biggest = max(code_modules, key=lambda m: m.lines)
        if biggest.lines >= 0.5 * max(1, result.total_lines):
            result.package_root = biggest.name
    if not result.test_files:
        result.notes.append(
            "no test files found — a build here has no suite to keep green, "
            "which every later gate assumes"
        )
    if result.total_files >= cap:
        result.notes.append(f"file scan capped at {cap}; the map is partial")
    return result


def derive_deps(map_: CodebaseMap) -> dict:
    """The observed module graph in `.mas/deps.yaml` shape.

    This is what the code does today, offered as the starting allowed graph so
    the arch fitness function has something real to check against instead of a
    hand-written file nobody writes. It is explicitly a baseline, not a design:
    the `derived_from` note keeps that visible in the artifact, and tightening
    it is the operator's job.
    """
    modules: dict[str, dict] = {}
    for facts in map_.modules:
        if facts.name in (".", "tests", "test", "docs"):
            continue
        modules[facts.name] = {
            "may_import": facts.imports or [],
            "public": [],
        }
    # load_deps() closes the graph: an edge to something undeclared is an
    # error, so drop edges that point outside the module set.
    for spec in modules.values():
        spec["may_import"] = [t for t in spec["may_import"] if t in modules]
    return {
        "derived_from": "avs map (observed imports, not a declared design)",
        "modules": modules,
    }


def write_map(map_: CodebaseMap, repo_dir: str | pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(repo_dir) / ".mas" / "codebase-map.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(map_.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def render_summary(map_: CodebaseMap, *, cap_modules: int = 25) -> str:
    """The map as prompt context — what a planner needs to integrate with an
    existing product, instead of a truncated list of file paths."""
    languages = ", ".join(
        f"{lang} ({count} files)"
        for lang, count in sorted(map_.languages.items(), key=lambda kv: -kv[1])
    ) or "no recognized source files"
    lines = [
        f"languages: {languages}",
        f"size: {map_.total_files} files, {map_.total_lines} lines",
    ]
    if map_.package_root:
        lines.append(f"package root: {map_.package_root}")
    if map_.entry_points:
        lines.append(f"entry points: {', '.join(map_.entry_points[:8])}")
    lines.append("modules:")
    for facts in sorted(map_.modules, key=lambda m: -m.lines)[:cap_modules]:
        edge = f" → {', '.join(facts.imports)}" if facts.imports else ""
        lines.append(
            f"  - {facts.name} ({facts.files} files, {facts.lines} lines,"
            f" {'/'.join(facts.languages)}){edge}"
        )
    if map_.routes:
        lines.append(f"http surface ({len(map_.routes)}):")
        lines += [f"  - {route}" for route in map_.routes[:40]]
    if map_.test_files:
        lines.append(f"tests: {len(map_.test_files)} file(s), "
                     f"e.g. {', '.join(map_.test_files[:5])}")
    for note in map_.notes:
        lines.append(f"note: {note}")
    return "\n".join(lines)
