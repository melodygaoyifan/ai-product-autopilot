"""Module-spec invariant layer (docs 08/11 §16.3, plan phase C item 11).

`.mas/specs/*.spec.yaml` records per-MODULE invariants (feature specs live
elsewhere): what must stay true, which side effects are forbidden, and
which change patterns are expected vs suspicious. spec_drift_check turns a
diff into findings: a change matching unexpected_change_pattern — or
touching the module outside every expected pattern — is
SPEC_DRIFT_UNDOCUMENTED, the erosion signal doc 08 names.
"""

from __future__ import annotations

import fnmatch
import pathlib
import re

import yaml
from pydantic import BaseModel, Field


class ModuleSpec(BaseModel):
    module: str
    paths: list[str]  # globs owned by the module
    invariants: list[str] = Field(default_factory=list)
    allowed_error_classes: list[str] = Field(default_factory=list)
    forbidden_side_effects: list[str] = Field(default_factory=list)  # regexes
    expected_change_pattern: list[str] = Field(default_factory=list)  # globs
    unexpected_change_pattern: list[str] = Field(default_factory=list)  # globs


class ModuleSpecError(RuntimeError):
    pass


def load_module_specs(mas_dir: str | pathlib.Path) -> list[ModuleSpec]:
    specs_dir = pathlib.Path(mas_dir) / "specs"
    specs = []
    for path in sorted(specs_dir.glob("*.spec.yaml")):
        raw = yaml.safe_load(path.read_text()) or {}
        if not raw.get("module") or not raw.get("paths"):
            raise ModuleSpecError(f"{path.name}: module and paths are required")
        specs.append(ModuleSpec(**raw))
    return specs


class DriftFinding(BaseModel):
    module: str
    rule: str  # SPEC_DRIFT_UNDOCUMENTED | forbidden_side_effect
    file: str
    message: str


def spec_drift_check(
    specs: list[ModuleSpec], files_changed: list[str],
    added_lines: dict[str, str] | None = None,
) -> list[DriftFinding]:
    findings = []
    for spec in specs:
        owned = [f for f in files_changed
                 if any(fnmatch.fnmatch(f, g) for g in spec.paths)]
        for file in owned:
            if any(fnmatch.fnmatch(file, g) for g in spec.unexpected_change_pattern):
                findings.append(DriftFinding(
                    module=spec.module, rule="SPEC_DRIFT_UNDOCUMENTED", file=file,
                    message="change matches an unexpected pattern — document "
                            "the intent via SCR or the spec is drifting"))
            elif spec.expected_change_pattern and not any(
                fnmatch.fnmatch(file, g) for g in spec.expected_change_pattern
            ):
                findings.append(DriftFinding(
                    module=spec.module, rule="SPEC_DRIFT_UNDOCUMENTED", file=file,
                    message="change outside every expected pattern for this "
                            "module — undocumented drift"))
            for pattern in spec.forbidden_side_effects:
                text = (added_lines or {}).get(file, "")
                match = re.search(pattern, text)
                if match:
                    findings.append(DriftFinding(
                        module=spec.module, rule="forbidden_side_effect",
                        file=file,
                        message=f"forbidden side effect {match.group(0)!r} "
                                f"(spec pattern {pattern!r})"))
    return findings
