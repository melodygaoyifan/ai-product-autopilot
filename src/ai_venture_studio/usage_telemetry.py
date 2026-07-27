"""Usage telemetry (ADR-U28) — opt-in, aggregate-only, inspectable.

Default OFF. The payload is schema-pinned: version, edition, substrate
rung, stage-completion counts, gate-outcome counts, error classes — and
structurally nothing else (the builder has no access to content fields).
Never: FDR content, code, prompts, model outputs, repo names, claim text.
`avs telemetry show` prints the exact next payload before anything
would send; no endpoint is configured in this version, so nothing sends at
all — the spool is the whole story. §22.64's taint rules would be absurd
to preach if our own telemetry didn't clear them.
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter

import yaml
from importlib.metadata import PackageNotFoundError, version

TELEMETRY_FILE = "telemetry.yaml"
SCHEMA_VERSION = 1
# The complete, closed field set. A PR adding a field here is a
# major-version review with a `telemetry show` diff (F-25.3).
PAYLOAD_FIELDS = (
    "schema_version",
    # Wire field name kept across the rename: a telemetry consumer parsing
    # `autoproduct_version` must not break because we renamed ourselves.
    "autoproduct_version",
    "edition",
    "substrate_rung",
    "stage_completion_counts",
    "gate_outcome_counts",
    "error_classes",
)


def _mas(workspace: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(workspace) / ".mas"


def telemetry_enabled(workspace: str | pathlib.Path) -> bool:
    path = _mas(workspace) / TELEMETRY_FILE
    if not path.exists():
        return False  # default off, always
    raw = yaml.safe_load(path.read_text()) or {}
    return bool(raw.get("enabled"))


def set_telemetry(workspace: str | pathlib.Path, enabled: bool) -> pathlib.Path:
    path = _mas(workspace) / TELEMETRY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"enabled": enabled}))
    return path


def build_payload(workspace: str | pathlib.Path) -> dict:
    """The exact next payload — aggregate counts only, by construction."""
    mas = _mas(workspace)
    try:
        # The distribution was renamed autoproduct -> ai-venture-studio
        # (v0.54). Try the current name, fall back to the old one so an
        # existing install still reports a version instead of "unknown".
        try:
            pkg_version = version("ai-venture-studio")
        except PackageNotFoundError:
            pkg_version = version("autoproduct")
    except PackageNotFoundError:
        pkg_version = "unknown"

    edition, rung = "none", "unknown"
    edition_path = mas / "edition.yaml"
    if edition_path.exists():
        raw = yaml.safe_load(edition_path.read_text()) or {}
        edition = str(raw.get("edition", "none"))
        rung = str((raw.get("defaults") or {}).get("substrate_rung", "unknown"))

    verdicts: Counter[str] = Counter()
    stages: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    reviews = mas / "reviews"
    if reviews.is_dir():
        for review in sorted(reviews.iterdir()):
            meta = review / "meta.yaml"
            if not meta.is_file():
                continue
            raw = yaml.safe_load(meta.read_text()) or {}
            verdict = str(raw.get("verdict") or "unknown")
            verdicts[verdict] += 1
            stages[f"steps_{len(list(review.glob('[0-9]*.yaml')))}"] += 1
            if verdict.startswith("ESCALATE"):
                errors[verdict] += 1

    payload = {
        "schema_version": SCHEMA_VERSION,
        "autoproduct_version": pkg_version,
        "edition": edition,
        "substrate_rung": rung,
        "stage_completion_counts": dict(stages),
        "gate_outcome_counts": dict(verdicts),
        "error_classes": dict(errors),
    }
    if set(payload) != set(PAYLOAD_FIELDS):
        raise AssertionError("telemetry payload drifted from its pinned schema")
    return payload


def render_payload(workspace: str | pathlib.Path) -> str:
    return json.dumps(build_payload(workspace), indent=2, sort_keys=True)
