"""The kill registry read path (§22.65.2, §20.54.3).

P5 writes this registry (a later milestone); the READER ships first
because P0's Novelty voter depends on it — a killed idea returning as a
fresh opportunity must be surfaced with its history, including the case
where circumstances genuinely changed (that is why reasons are kept, not
just verdicts). Append-only; `reusable_learning` and `revisit_if` are what
make it an asset rather than a graveyard.
"""

from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field

from ai_venture_studio.textsim import similarity

KILL_REGISTRY_FILE = "kill-registry.yaml"
DEFAULT_MATCH_THRESHOLD = 0.30  # statements are short; shingle overlap is sparse


class KillRecord(BaseModel):
    id: str
    decided_at: str
    outcome: str  # kill | pivot
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    hypotheses_falsified: list[str] = Field(default_factory=list)
    reusable_learning: str = ""
    revisit_if: str = ""
    statement: str = ""  # what the killed idea was, for matching


class KillRegistryError(RuntimeError):
    """Malformed registry. Append-only history that cannot be read is lost
    history — fail loudly."""


class KillMatch(BaseModel):
    record: KillRecord
    score: float


def load_kill_registry(mas_dir: str | pathlib.Path) -> list[KillRecord]:
    path = pathlib.Path(mas_dir) / KILL_REGISTRY_FILE
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise KillRegistryError(f"{KILL_REGISTRY_FILE}: {exc}") from exc
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise KillRegistryError(f"{KILL_REGISTRY_FILE} must be a list (append-only)")
    try:
        return [KillRecord(**entry) for entry in raw]
    except (TypeError, ValueError) as exc:
        raise KillRegistryError(f"{KILL_REGISTRY_FILE}: {exc}") from exc


def match_killed(
    candidate_statement: str,
    registry: list[KillRecord],
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> list[KillMatch]:
    """Surface killed/pivoted work resembling a candidate — with its
    history, so a human can judge whether `revisit_if` has come true."""
    matches = [
        KillMatch(record=record, score=score)
        for record in registry
        if (
            # k=2: kill statements are a dozen words; word-pair overlap is
            # the signal, five-word shingles never intersect at this length.
            score := similarity(
                candidate_statement, f"{record.statement} {record.reason}", k=2
            )
        )
        >= threshold
    ]
    return sorted(matches, key=lambda m: m.score, reverse=True)
