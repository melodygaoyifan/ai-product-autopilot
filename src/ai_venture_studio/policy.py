"""Per-project policy thresholds (doc 09 open item: "policy thresholds in
project.yaml").

The engineering defaults live in code and stay the defaults; a project may
override them in `.mas/project.yaml` under a `policy:` block:

    policy:
      max_reviewable_lines: 1200     # Gate 1 DoR ceiling
      report_threshold: 85           # composite score to report a finding
      high_severity_threshold: 55    # ... at critical/high severity
      rootcause_confidence_min: 70   # below this, Maintenance escalates

Three rules keep this from becoming a quiet way to weaken the system:

1. **Unknown keys are an error**, never ignored — a typo that silently
   kept the default would be worse than a crash (`PolicyError`).
2. **Ranges are enforced**, and each threshold has a floor/ceiling the
   project cannot cross: gates may be made *stricter* freely, but the
   loosest admissible value is bounded.
3. **Effective values are recorded** with every run (`as_dict()` goes into
   the review mirror), and any value looser than the default is labeled in
   `weakened()` so a report never hides the fact that its bar was lowered.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import yaml

POLICY_KEY = "policy"

# (default, hard floor, hard ceiling) per threshold. "Looser" differs per
# threshold: a bigger diff ceiling is looser, a smaller score bar is looser.
#
# The defaults duplicate the module-level constants they replace
# (graph.MAX_REVIEWABLE_LINES, scoring.REPORT_THRESHOLD,
# scoring.HIGH_SEVERITY_THRESHOLD, maintenance CONFIDENCE_MIN) rather than
# importing them — those modules import this one. test_policy.py asserts
# the two agree, so drift fails the suite instead of going unnoticed.
_BOUNDS = {
    "max_reviewable_lines": (2000, 50, 5000),
    "report_threshold": (80, 50, 100),
    "high_severity_threshold": (60, 40, 100),
    "rootcause_confidence_min": (60, 40, 100),
}
# Which direction is a weakening, for the honesty label.
_LOOSER_WHEN_HIGHER = {"max_reviewable_lines"}


class PolicyError(RuntimeError):
    """A policy block that cannot be honored — fail loudly, never default."""


@dataclass(frozen=True)
class Policy:
    max_reviewable_lines: int = _BOUNDS["max_reviewable_lines"][0]
    report_threshold: int = _BOUNDS["report_threshold"][0]
    high_severity_threshold: int = _BOUNDS["high_severity_threshold"][0]
    rootcause_confidence_min: int = _BOUNDS["rootcause_confidence_min"][0]

    def as_dict(self) -> dict[str, int]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def weakened(self) -> list[str]:
        """Thresholds set looser than the shipped default, as labels for the
        report. Stricter-than-default needs no announcement."""
        notes = []
        for name, (default, _floor, _ceiling) in _BOUNDS.items():
            value = getattr(self, name)
            looser = (
                value > default
                if name in _LOOSER_WHEN_HIGHER
                else value < default
            )
            if looser:
                notes.append(f"{name}={value} (default {default})")
        return notes


def load_policy(repo_dir: str | Path) -> Policy:
    """Read `.mas/project.yaml` → `policy:`; absent file or block = defaults."""
    path = Path(repo_dir) / ".mas" / "project.yaml"
    if not path.exists():
        return Policy()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise PolicyError(f"{path} is not parseable YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise PolicyError(f"{path} must be a mapping")
    block = data.get(POLICY_KEY) or {}
    if not isinstance(block, dict):
        raise PolicyError(f"{path}: `{POLICY_KEY}` must be a mapping")

    unknown = sorted(set(block) - set(_BOUNDS))
    if unknown:
        raise PolicyError(
            f"{path}: unknown policy key(s) {unknown}; known keys are "
            f"{sorted(_BOUNDS)} — a typo that silently kept the default is "
            "worse than this error"
        )
    values = {}
    for name, raw in block.items():
        default, floor, ceiling = _BOUNDS[name]
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise PolicyError(f"{path}: policy.{name} must be an integer, got {raw!r}")
        if not floor <= raw <= ceiling:
            raise PolicyError(
                f"{path}: policy.{name}={raw} is outside the admissible range "
                f"[{floor}, {ceiling}] — the system refuses to run with a bar "
                "it considers meaningless"
            )
        values[name] = raw
    return Policy(**values)
