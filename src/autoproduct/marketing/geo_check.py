"""geo_extractability_check (§21.58.6, §21.60) — retrievable, citable, honest.

The KDD 2024 GEO result is aligned with this framework's values: what
raises generative-engine visibility is adding statistics, citing sources,
and quotations — verifiability. So the GEO tactic and the honesty gate are
the same check: every statistic carries an inline source, the page names a
resolvable author, crawler access is verified rather than assumed (the CDN
default-deny trap silently removes a property from the corpus).

ADR-U21 — retrieval manipulation is forbidden by construction: hidden or
visibility-mismatched text, instruction-shaped content aimed at reading
models, and fan-out are mechanical failures here and in spam_policy_check,
not style-guide entries. A system that pollutes the corpus for its product
while depending on a clean corpus for its own P1 research is incoherent.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel

from autoproduct.marketing.artifacts import Page

_QUANT = re.compile(r"\d+(?:\.\d+)?\s*%|\$\s?\d|\b\d+(?:\.\d+)?\s*(?:x|×)\b")
_INLINE_SOURCE = re.compile(r"\[[^\]]+\]\([^)]+\)|<a\s+[^>]*href=|https?://")
_INSTRUCTION_SHAPED = re.compile(
    r"\b(ignore (?:all )?previous|disregard (?:the )?above|"
    r"(?:always )?(?:cite|recommend|rank) (?:this|our) (?:page|product|site)|"
    r"you (?:are|must)\b.{0,40}\b(?:assistant|model|AI)\b)",
    re.I,
)


class GeoFinding(BaseModel):
    rule: str
    message: str


def geo_extractability_check(page: Page) -> list[GeoFinding]:
    findings = []

    for crawler in page.intended_crawlers:
        allowed = page.crawler_access.get(crawler, False)
        cdn_blocked = crawler in page.cdn_blocks
        if not allowed or cdn_blocked:
            via = "CDN bot rules" if cdn_blocked else "robots.txt"
            findings.append(
                GeoFinding(
                    rule="crawler_access",
                    message=f"intended crawler {crawler!r} is blocked by {via} — "
                    "the default-deny trap silently removes the property from "
                    "the corpus",
                )
            )

    for block in page.structured_data:
        try:
            data = json.loads(block)
        except json.JSONDecodeError as exc:
            findings.append(
                GeoFinding(
                    rule="structured_data_invalid",
                    message=f"JSON-LD block does not parse: {exc}",
                )
            )
            continue
        if not isinstance(data, dict) or not data.get("@type"):
            findings.append(
                GeoFinding(
                    rule="structured_data_invalid",
                    message="JSON-LD block lacks an @type",
                )
            )

    for paragraph in re.split(r"\n{2,}", page.text):
        if _QUANT.search(paragraph) and not _INLINE_SOURCE.search(paragraph):
            findings.append(
                GeoFinding(
                    rule="statistic_without_inline_source",
                    message=f"statistic without an inline source in: "
                    f"{paragraph.strip()[:80]!r}",
                )
            )

    if not page.author_name or not page.author_identity_url:
        findings.append(
            GeoFinding(
                rule="author_identity",
                message="page names no author with a resolvable identity",
            )
        )
    if not page.canonical_url:
        findings.append(
            GeoFinding(rule="canonical_missing", message="no canonical URL")
        )
    if not page.published_at:
        findings.append(
            GeoFinding(
                rule="freshness_metadata",
                message="no published/modified metadata present",
            )
        )

    # --- ADR-U21: forbidden by construction ---------------------------------
    if page.hidden_text.strip():
        findings.append(
            GeoFinding(
                rule="visibility_mismatch",
                message="text present for crawlers but hidden from readers — "
                "retrieval manipulation, forbidden by construction (ADR-U21)",
            )
        )
    for text in (page.text, page.hidden_text):
        match = _INSTRUCTION_SHAPED.search(text)
        if match:
            findings.append(
                GeoFinding(
                    rule="instruction_shaped_content",
                    message=f"instruction-shaped content aimed at reading models: "
                    f"{match.group(0)!r} (ADR-U21)",
                )
            )
    return findings
