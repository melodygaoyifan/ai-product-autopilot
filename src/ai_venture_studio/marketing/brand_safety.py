"""brand_and_safety_scan (§21.58.5) — the deterministic pattern layer.

Banned-claim phrases from the compliance profile; competitor mentions
routed to a review flag (comparative advertising carries its own
substantiation duty, it is not automatically wrong); PII in outbound copy;
unresolved template variables ({{first_name}} shipping literally is the
canonical embarrassment); malformed links. Live link resolution is an
availability-gated wrapper at runtime — the structural checks here are
always on.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from ai_venture_studio.marketing.artifacts import Draft
from ai_venture_studio.marketing.disclosure import ComplianceProfile

_TEMPLATE_VAR = re.compile(r"\{\{\s*[\w.]+\s*\}\}|\{%[^%]*%\}|\$\{[\w.]+\}")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_PHONE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}\b")
_URL = re.compile(r"https?://\S+|href=[\"']([^\"']*)[\"']")


class BrandConfig(BaseModel):
    competitor_names: list[str] = Field(default_factory=list)
    banned_phrases_extra: list[str] = Field(default_factory=list)
    own_domains: list[str] = Field(default_factory=list)  # PII allowlist, e.g. support@


class BrandSafetyFinding(BaseModel):
    rule: str
    message: str
    review_flag: bool = False  # human judgment required, not automatically wrong


def brand_and_safety_scan(
    draft: Draft,
    profile: ComplianceProfile | None = None,
    brand: BrandConfig | None = None,
) -> list[BrandSafetyFinding]:
    profile = profile or ComplianceProfile()
    brand = brand or BrandConfig()
    findings = []
    text_lower = draft.text.lower()

    for phrase in [*profile.banned_phrases, *brand.banned_phrases_extra]:
        if phrase.lower() in text_lower:
            findings.append(
                BrandSafetyFinding(
                    rule="banned_phrase",
                    message=f"banned claim phrase {phrase!r} in draft",
                )
            )

    for name in brand.competitor_names:
        if re.search(rf"\b{re.escape(name)}\b", draft.text, re.I):
            findings.append(
                BrandSafetyFinding(
                    rule="competitor_mention",
                    message=f"competitor {name!r} mentioned — comparative "
                    "advertising has its own substantiation duty; routed to review",
                    review_flag=True,
                )
            )

    for match in _TEMPLATE_VAR.finditer(draft.text):
        findings.append(
            BrandSafetyFinding(
                rule="unresolved_template_variable",
                message=f"unresolved template variable {match.group(0)!r} would "
                "ship literally",
            )
        )

    for pattern, label in ((_EMAIL, "email address"), (_PHONE, "phone number")):
        for match in pattern.finditer(draft.text):
            value = match.group(0)
            if any(d and d.lower() in value.lower() for d in brand.own_domains):
                continue
            findings.append(
                BrandSafetyFinding(
                    rule="pii_in_copy",
                    message=f"{label} {value!r} in outbound copy",
                )
            )

    for match in _URL.finditer(draft.text):
        url = match.group(1) or match.group(0)
        if url.startswith(("http://", "https://")):
            continue
        findings.append(
            BrandSafetyFinding(
                rule="malformed_link",
                message=f"link {url!r} is not an absolute http(s) URL",
            )
        )
    return findings
