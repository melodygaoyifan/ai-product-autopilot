"""Signal sources and the standing rule (§20.54.2).

An opportunity is only as real as its signal. Sources are declared in
.mas/signal-sources.yaml and each carries a `standing` field — the reason
we are allowed to read it (first-party ours, public + official API, vendor
API). No standing, no source: the loader fails closed, matching
PolicyLoader semantics (§11.19).

`source_standing_check` then verifies that claim evidence actually comes
from declared sources: an evidence locator matching no declared source is
a finding — research from a surface nobody granted is not evidence.
"""

from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field

from autoproduct.product.claim_lint import ClaimIssue

SIGNAL_SOURCES_FILE = "signal-sources.yaml"

# Locator schemes that never need declared standing: our own stored
# artifacts and first-party systems inside the boundary.
_OWNED_PREFIXES = ("evidence://", "crm://", ".mas/evidence/")


class SignalSourceError(RuntimeError):
    """Raised when signal-sources.yaml is malformed or a source lacks
    standing. Fails closed — a source with no stated reason to read it
    is not a source."""


class SignalSource(BaseModel):
    id: str
    standing: str  # the reason we are allowed to read it
    match: list[str] = Field(default_factory=list)  # locator prefixes
    typed_as: str = ""  # default source_type for signals from here


def load_signal_sources(mas_dir: str | pathlib.Path) -> list[SignalSource]:
    """Load .mas/signal-sources.yaml, failing closed on any undeclared standing."""
    path = pathlib.Path(mas_dir) / SIGNAL_SOURCES_FILE
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise SignalSourceError(f"{SIGNAL_SOURCES_FILE} is not valid YAML: {exc}") from exc
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SignalSourceError(f"{SIGNAL_SOURCES_FILE} must be a list of sources")
    sources = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise SignalSourceError(f"source entry is not a mapping: {entry!r}")
        source_id = str(entry.get("id") or "?")
        if not str(entry.get("standing") or "").strip():
            raise SignalSourceError(
                f"source {source_id!r} declares no standing — no standing, no source"
            )
        sources.append(
            SignalSource(
                id=source_id,
                standing=str(entry["standing"]),
                match=[str(m) for m in entry.get("match") or []],
                typed_as=str(entry.get("typed_as") or ""),
            )
        )
    return sources


def source_standing_check(
    doc: dict, sources: list[SignalSource]
) -> list[ClaimIssue]:
    """Flag claim evidence whose locator matches no declared source."""
    issues = []
    for claim in doc.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        cid = str(claim.get("id", "?"))
        for entry in claim.get("evidence") or []:
            if not isinstance(entry, dict):
                continue
            locator = str(entry.get("locator") or "")
            if not locator or locator.startswith(_OWNED_PREFIXES):
                continue
            if any(
                locator.startswith(prefix) for s in sources for prefix in s.match
            ):
                continue
            issues.append(
                ClaimIssue(
                    claim_id=cid,
                    rule="undeclared_source",
                    message=f"locator {locator!r} matches no source declared in "
                    f".mas/{SIGNAL_SOURCES_FILE} — no standing, no source",
                )
            )
    return issues
