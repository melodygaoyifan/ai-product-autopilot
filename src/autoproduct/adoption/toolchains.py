"""Language toolchains as fixture-gated det_tools (§18.47.2, ADR-U16;
§19 G7-G9).

First-class means: the det_tools slot table exists for the language, every
wrapper is availability-gated (a missing binary reports `skipped` visibly —
silent absence reads as "scanned and clean"), and the toolchain's
seeded-defect catch-rate is measured against a planted-defect manifest
before it registers. Below the parity margin it registers as PROVISIONAL
with the lagging slots named in every banner (F-18.4). Voters stay
language-agnostic — nothing here touches a prompt.

Built-in argv are starting points; real projects override per slot in
`.mas/toolchains.yaml` (a Maven shop and a Gradle shop share no test argv).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

TOOLCHAINS_CONFIG = ".mas/toolchains.yaml"
REGISTRY_DIR = ".mas/toolchains"

SLOTS = ("lint", "tests", "mutation", "sast", "deps")

# §18.47.2 mapping table. `python` is the reference lane the parity margin
# is measured against.
_BUILTIN: dict[str, dict[str, list[str]]] = {
    "python": {
        "lint": ["ruff", "check", "."],
        "tests": ["pytest", "-q"],
        "mutation": ["mutmut", "run"],
        "sast": ["semgrep", "scan", "--error", "--quiet"],
        "deps": ["pip-audit"],
    },
    "java": {
        "lint": ["checkstyle", "-c", "/google_checks.xml", "src"],
        "tests": ["mvn", "-q", "test"],
        "mutation": ["mvn", "-q", "org.pitest:pitest-maven:mutationCoverage"],
        "sast": ["semgrep", "scan", "--error", "--quiet"],
        "deps": ["dependency-check", "--scan", "."],
    },
    "dotnet": {
        "lint": ["dotnet", "build", "-warnaserror"],
        "tests": ["dotnet", "test"],
        "mutation": ["dotnet", "stryker"],
        "sast": ["semgrep", "scan", "--error", "--quiet"],
        "deps": ["dotnet", "list", "package", "--vulnerable"],
    },
}


class SlotResult(BaseModel):
    slot: str
    status: str  # clean | findings | skipped | error
    detail: str = ""
    output: str = ""


class ToolchainReport(BaseModel):
    language: str
    results: list[SlotResult]

    @property
    def skipped_slots(self) -> list[str]:
        return [r.slot for r in self.results if r.status == "skipped"]


class DefectOutcome(BaseModel):
    defect_id: str
    slot: str
    caught: bool
    detail: str = ""


class BenchmarkResult(BaseModel):
    language: str
    outcomes: list[DefectOutcome]

    @property
    def catch_rate(self) -> float:
        if not self.outcomes:
            raise ValueError("empty manifest — a benchmark over nothing is not a measurement")
        return sum(o.caught for o in self.outcomes) / len(self.outcomes)

    def lagging_slots(self) -> list[str]:
        return sorted({o.slot for o in self.outcomes if not o.caught})


class ToolchainRecord(BaseModel):
    """What lands in .mas/toolchains/<language>.yaml — the fixture-gate
    receipt. `provisional` toolchains carry their named gaps into banners."""

    language: str
    status: str  # registered | provisional
    catch_rate: float
    baseline_rate: float
    parity_margin: float
    gaps: list[str] = Field(default_factory=list)


def toolchain_spec(repo_dir: str | Path, language: str) -> dict[str, list[str]]:
    """Built-in slot table overlaid with per-project overrides."""
    if language not in _BUILTIN:
        raise ValueError(f"unknown language {language!r}; known: {sorted(_BUILTIN)}")
    spec = {slot: list(argv) for slot, argv in _BUILTIN[language].items()}
    path = Path(repo_dir) / TOOLCHAINS_CONFIG
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for slot, argv in (data.get(language) or {}).items():
            if slot not in SLOTS:
                raise ValueError(f"{path}: unknown slot {slot!r}; known: {list(SLOTS)}")
            if not isinstance(argv, list) or not argv:
                raise ValueError(f"{path}: {language}.{slot} must be a non-empty argv list")
            spec[slot] = [str(a) for a in argv]
    return spec


def run_slot(repo_dir: str | Path, slot: str, argv: list[str], timeout_s: int = 600) -> SlotResult:
    executable = shutil.which(argv[0])
    if executable is None:
        return SlotResult(
            slot=slot, status="skipped",
            detail=f"{argv[0]} not on PATH — NOT scanned, not clean",
        )
    try:
        proc = subprocess.run(
            [executable, *argv[1:]],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return SlotResult(slot=slot, status="error", detail=f"timeout after {timeout_s}s")
    output = (proc.stdout or "") + (proc.stderr or "")
    status = "clean" if proc.returncode == 0 else "findings"
    return SlotResult(slot=slot, status=status, detail=f"exit {proc.returncode}", output=output)


def run_toolchain(
    repo_dir: str | Path, language: str, spec: dict[str, list[str]] | None = None
) -> ToolchainReport:
    resolved = spec if spec is not None else toolchain_spec(repo_dir, language)
    results = [run_slot(repo_dir, slot, argv) for slot, argv in resolved.items()]
    return ToolchainReport(language=language, results=results)


def load_seeded_manifest(path: str | Path) -> list[dict]:
    """Planted-defect manifest (§19 G7): defects: [{id, slot, pattern}] —
    pattern is a substring the slot's output must contain when it catches."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    defects = data.get("defects", [])
    if not defects:
        raise ValueError(f"{path}: manifest has no defects — nothing to measure")
    for i, d in enumerate(defects):
        missing = {"id", "slot", "pattern"} - set(d)
        if missing:
            raise ValueError(f"{path}: defect {i} missing {sorted(missing)}")
        if d["slot"] not in SLOTS:
            raise ValueError(f"{path}: defect {d['id']} names unknown slot {d['slot']!r}")
    return defects


def benchmark_toolchain(report: ToolchainReport, defects: list[dict]) -> BenchmarkResult:
    by_slot = {r.slot: r for r in report.results}
    outcomes = []
    for d in defects:
        result = by_slot.get(d["slot"])
        if result is None or result.status == "skipped":
            outcomes.append(DefectOutcome(
                defect_id=d["id"], slot=d["slot"], caught=False,
                detail="slot skipped — a missing scanner catches nothing",
            ))
        elif result.status == "error":
            outcomes.append(DefectOutcome(
                defect_id=d["id"], slot=d["slot"], caught=False, detail=result.detail,
            ))
        else:
            caught = d["pattern"] in result.output
            outcomes.append(DefectOutcome(
                defect_id=d["id"], slot=d["slot"], caught=caught,
                detail="" if caught else f"pattern {d['pattern']!r} absent from {d['slot']} output",
            ))
    return BenchmarkResult(language=report.language, outcomes=outcomes)


def register_toolchain(
    repo_dir: str | Path,
    result: BenchmarkResult,
    baseline_rate: float,
    parity_margin: float = 0.10,
) -> ToolchainRecord:
    """The fixture gate for toolchains: registration always records the
    measured number; below (baseline - margin) the status is PROVISIONAL
    with the lagging slots named — never a silent pass (F-18.4)."""
    if not 0.0 <= baseline_rate <= 1.0:
        raise ValueError(f"baseline_rate {baseline_rate} outside [0, 1]")
    rate = result.catch_rate
    provisional = rate < baseline_rate - parity_margin
    record = ToolchainRecord(
        language=result.language,
        status="provisional" if provisional else "registered",
        catch_rate=round(rate, 4),
        baseline_rate=round(baseline_rate, 4),
        parity_margin=parity_margin,
        gaps=result.lagging_slots() if provisional else [],
    )
    out_dir = Path(repo_dir) / REGISTRY_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{result.language}.yaml").write_text(
        yaml.safe_dump(record.model_dump(), sort_keys=False), encoding="utf-8"
    )
    return record


def toolchain_banner(repo_dir: str | Path, language: str) -> str | None:
    """Verdict-banner line for a registered toolchain; None when the
    language was never benchmarked (unmeasured ≠ registered)."""
    path = Path(repo_dir) / REGISTRY_DIR / f"{language}.yaml"
    if not path.exists():
        return None
    record = ToolchainRecord(**yaml.safe_load(path.read_text(encoding="utf-8")))
    if record.status == "provisional":
        return (
            f"toolchain {language} PROVISIONAL (catch-rate "
            f"{record.catch_rate:.0%} vs baseline {record.baseline_rate:.0%}; "
            f"lagging: {', '.join(record.gaps)})"
        )
    return f"toolchain {language} registered (catch-rate {record.catch_rate:.0%})"
