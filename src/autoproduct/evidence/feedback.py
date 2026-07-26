"""The feedback boundary (§23 week P6) — tickets, reviews, survey text.

Same egress rules as analytics: PII-redacted, aggregate-first. The extra
duty here is provenance: every stored artifact gets a locator that
resolves into .mas/evidence/, so a `user_reported` claim built on it can
be verified (and synthetic_persona_scan can prove a quote is real). An
agent may cluster and count these artifacts; it may never author one
(ADR-U23).
"""

from __future__ import annotations

import pathlib
import re
from collections import Counter

from pydantic import BaseModel

from autoproduct.evidence.analytics import pii_scan
from autoproduct.product.evidence import resolve_snapshot, store_snapshot


class FeedbackArtifact(BaseModel):
    locator: str  # evidence://<sha256> — resolves into .mas/evidence/
    kind: str  # ticket | review | survey | interview | sales_note
    source_id: str  # declared signal source (§20.54.2)
    text_redacted: str


class FeedbackStore:
    """Ingests real user artifacts, snapshots them, and serves aggregates."""

    def __init__(self, mas_dir: str | pathlib.Path) -> None:
        self._mas_dir = pathlib.Path(mas_dir)
        self._artifacts: list[FeedbackArtifact] = []

    def ingest(self, text: str, *, kind: str, source_id: str) -> FeedbackArtifact:
        """Store the raw artifact (verbatim, hashed) and expose only the
        redacted text. The raw snapshot is what locators resolve to."""
        snapshot = store_snapshot(text.encode(), self._mas_dir, suffix=".txt")
        artifact = FeedbackArtifact(
            locator="evidence://" + snapshot.artifact_hash.removeprefix("sha256:"),
            kind=kind,
            source_id=source_id,
            text_redacted=pii_scan(text),
        )
        self._artifacts.append(artifact)
        return artifact

    def resolve(self, locator: str) -> pathlib.Path | None:
        """A user_reported claim's locator must resolve to a stored artifact."""
        digest = locator.removeprefix("evidence://")
        return resolve_snapshot(f"sha256:{digest}", self._mas_dir)

    def cluster_counts(self, pattern: str) -> dict[str, int]:
        """Count artifacts matching a pattern, by kind — a persona is a
        summary of counted artifacts, always carrying its n (§20.53.4)."""
        regex = re.compile(pattern, re.I)
        counts: Counter[str] = Counter()
        for artifact in self._artifacts:
            if regex.search(artifact.text_redacted):
                counts[artifact.kind] += 1
        return dict(counts)

    def quotes(self, pattern: str, *, limit: int = 10) -> list[FeedbackArtifact]:
        """Matching artifacts, redacted, each carrying its resolvable locator."""
        regex = re.compile(pattern, re.I)
        return [a for a in self._artifacts if regex.search(a.text_redacted)][:limit]
