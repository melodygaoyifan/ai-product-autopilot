"""Editions (doc 24, ADR-U26/U27) — narrowing preset bundles, never forks.

An edition is one YAML file resolved at `avs init --edition <e>`:
default substrate rung, WIP, channels, cadence ceilings, gate-consolidation
policy, docs entry. Editions may NARROW (consolidate gates per explicit
rules, lower WIP, lower ceilings) and may never WIDEN (skip a stage, remove
a deterministic check, raise a ceiling, drop a never-consolidate class).
`edition_lint` enforces that at init — narrowing-only, enforced, not
documented-and-hoped (invariant 14.21). Gate consolidation is scheduling,
never deletion: batched gates produce identical records (invariant 14.22).
"""

from __future__ import annotations

import pathlib
import re

import yaml
from pydantic import BaseModel, Field

from ai_venture_studio.marketing.channels import BUILTIN_CHANNELS

EDITIONS = ("enterprise", "solo", "engineer")
from ai_venture_studio.paths import editions_root

EDITIONS_ROOT = editions_root()

# The non-editable floor: these gate classes never batch (§70.1).
NEVER_CONSOLIDATE_FLOOR = frozenset(
    {"PL5", "incident", "consent_override", "gate3_sensitive"}
)
# Keys whose only purpose would be widening; presence fails, whatever the value.
_FORBIDDEN_KEYS = frozenset(
    {"skip_stages", "stages_disabled", "disable_checks", "disable_stage",
     "forbidden_autonomous_remove", "allow_autonomous"}
)
_ALLOWED_TOP = frozenset(
    {"edition", "version", "defaults", "gate_policy", "attention", "docs_entry"}
)
_RUNG = re.compile(r"^S([0-4])$")


def _framework_ceiling(channel: str) -> int | None:
    cadence = BUILTIN_CHANNELS.get(channel, {}).get("cadence", {})
    return min(cadence.values()) if cadence else None


def _parse_rate(value) -> int:
    """'2/week' → 2; bare ints pass through."""
    if isinstance(value, int):
        return value
    match = re.match(r"^\s*(\d+)\s*/", str(value))
    if not match:
        raise ValueError(f"cadence value {value!r} is not 'N/period' or an int")
    return int(match.group(1))


class EditionError(RuntimeError):
    """An edition file that widens, or that the harness does not recognize.
    Init refuses — a preset the lint cannot vouch for configures nothing."""


class Edition(BaseModel):
    edition: str
    version: int = 1
    defaults: dict = Field(default_factory=dict)
    gate_policy: dict = Field(default_factory=dict)
    attention: dict = Field(default_factory=dict)
    docs_entry: str = ""


def edition_lint(raw: dict) -> list[str]:
    """Named findings; any finding refuses the edition (invariant 14.21)."""
    findings: list[str] = []
    if not isinstance(raw, dict):
        return ["edition file must be a mapping"]

    unknown = set(raw) - _ALLOWED_TOP
    widening = unknown & _FORBIDDEN_KEYS
    if widening:
        findings.append(f"widening keys {sorted(widening)} — editions narrow, never widen")
    elif unknown:
        findings.append(f"unknown edition keys {sorted(unknown)} — the harness "
                        "refuses what it cannot vouch for (invariant 14.21)")

    if raw.get("edition") not in EDITIONS:
        findings.append(f"edition must be one of {EDITIONS}")

    defaults = raw.get("defaults") or {}
    rung = str(defaults.get("substrate_rung", "S0"))
    if not _RUNG.match(rung):
        findings.append(f"substrate_rung {rung!r} is not S0..S4 — editions may set "
                        "lower defaults, never disable the ladder")
    for channel, value in (defaults.get("cadence_ceilings") or {}).items():
        framework = _framework_ceiling(str(channel))
        try:
            requested = _parse_rate(value)
        except ValueError as exc:
            findings.append(str(exc))
            continue
        if framework is not None and requested > framework:
            findings.append(
                f"cadence ceiling {channel}={requested} raises the framework "
                f"ceiling {framework} — ceilings may be lowered, never raised"
            )

    policy = raw.get("gate_policy") or {}
    consolidation = policy.get("consolidation", "none")
    if consolidation not in ("none", "weekly_review"):
        findings.append(f"consolidation {consolidation!r} not in none|weekly_review")
    declared = set(policy.get("never_consolidate") or [])
    missing = NEVER_CONSOLIDATE_FLOOR - declared
    if missing:
        findings.append(
            f"never_consolidate drops {sorted(missing)} — the floor is not "
            "editable (§72.1); consolidation is scheduling, never deletion"
        )
    rung_number = int(_RUNG.match(rung).group(1)) if _RUNG.match(rung) else 0
    if rung_number >= 2 and not policy.get("require_gate_owner", False):
        findings.append(
            "require_gate_owner: false with substrate_rung >= S2 — the "
            "12%-conversion profile has a named owner per gate (§69.1)"
        )
    return findings


def load_edition_preset(name: str) -> dict:
    path = EDITIONS_ROOT / name / "edition.yaml"
    if not path.exists():
        raise EditionError(f"no edition preset at {path}")
    raw = yaml.safe_load(path.read_text()) or {}
    findings = edition_lint(raw)
    if findings:
        raise EditionError(f"edition {name!r} fails lint: " + "; ".join(findings))
    return raw


def resolve_edition(workspace: str | pathlib.Path, name: str) -> pathlib.Path:
    """Lint the preset and write it into the workspace (.mas/edition.yaml).
    Resolution order downstream: framework defaults → edition → domain
    profile(s) → substrate profile → workspace file; later may only narrow."""
    raw = load_edition_preset(name)
    target = pathlib.Path(workspace) / ".mas" / "edition.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(raw, sort_keys=False))
    return target


def load_workspace_edition(workspace: str | pathlib.Path) -> Edition | None:
    path = pathlib.Path(workspace) / ".mas" / "edition.yaml"
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text()) or {}
    findings = edition_lint(raw)
    if findings:
        raise EditionError("workspace edition fails lint: " + "; ".join(findings))
    return Edition(**raw)
