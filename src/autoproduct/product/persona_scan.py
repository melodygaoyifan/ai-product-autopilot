"""synthetic_persona_scan (§20.53.4) — the synthetic-user prohibition.

Agents may not generate user needs: they may quote, cluster, and count
real artifacts, never author one. A synthetic persona quote is
indistinguishable in form from a real one and will be read as evidence at
a scope gate — and in the marketing direction, fabricated testimonials are
per-se illegal under the amended FTC Endorsement Guides (ADR-U23).

The check is deterministic: every first-person-singular quoted string in a
P-stage artifact must appear verbatim inside a stored evidence snapshot
(.mas/evidence/). A quote no stored artifact contains was authored, not
reported.
"""

from __future__ import annotations

import pathlib
import re

from pydantic import BaseModel

from autoproduct.product.evidence import EVIDENCE_DIR

_QUOTED = re.compile(r'"([^"\n]{10,400})"|“([^”\n]{10,400})”')
_FIRST_PERSON = re.compile(r"\b(I|I'm|I've|I'd|my|me|we|we're|our)\b")


class PersonaFinding(BaseModel):
    rule: str = "synthetic_testimonial"
    quote: str
    message: str


def _stored_texts(mas_dir: str | pathlib.Path) -> list[str]:
    root = pathlib.Path(mas_dir) / EVIDENCE_DIR
    if not root.is_dir():
        return []
    texts = []
    for path in sorted(root.iterdir()):
        if path.is_file():
            texts.append(path.read_text(errors="replace"))
    return texts


def _normalize(text: str) -> str:
    # Embedding a real quote in prose legitimately re-punctuates its tail
    # ("…by hand," vs "…by hand"); punctuation is not fabrication.
    return re.sub(r"\s+", " ", text).strip().rstrip(".,;:!?")


def synthetic_persona_scan(
    artifact_text: str, mas_dir: str | pathlib.Path
) -> list[PersonaFinding]:
    """Flag first-person quotes that resolve to no stored evidence artifact."""
    stored = [_normalize(t) for t in _stored_texts(mas_dir)]
    findings = []
    for match in _QUOTED.finditer(artifact_text):
        quote = match.group(1) or match.group(2)
        if not _FIRST_PERSON.search(quote):
            continue
        needle = _normalize(quote)
        if any(needle in text for text in stored):
            continue
        findings.append(
            PersonaFinding(
                quote=quote,
                message="first-person quote resolves to no stored artifact in "
                ".mas/evidence/ — a persona is a summary of counted artifacts, "
                "never a character (ADR-U23)",
            )
        )
    return findings
