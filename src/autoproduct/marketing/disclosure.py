"""disclosure_lint (§21.58.2) — required disclosures, in the content itself.

The ruleset is config-driven per jurisdiction (.mas/compliance-profile.yaml)
because this area moves fast; the check is what makes it enforceable. The
profile carries a verified_on date and review cadence, and the check FAILS
CLOSED on an expired ruleset rather than passing on old rules (risk R-P4)
— same posture as `expires` on claims.

OPERATOR NOTE (§21.58.2 verify-at-adoption): the shipped default ruleset is
deliberately conservative and is the *shape* of the obligation, not legal
advice. Confirm jurisdiction specifics (state statutes, EU AI Act dates,
sector rules) with counsel and record the confirmation in
.mas/compliance-profile.yaml's verified_on.

The endorsement row is enforced hardest: §20.53.4 already forbids synthetic
user artifacts at the source, so no testimonial can legally reach a draft;
this lint is the second line, catching first-person experience prose the
writer generated directly (16 CFR Part 255 reaches AI-generated reviews).
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

import yaml
from pydantic import BaseModel, Field

from autoproduct.marketing.artifacts import Draft
from autoproduct.marketing.register import ReleaseContract

COMPLIANCE_PROFILE_FILE = "compliance-profile.yaml"

_FIRST_PERSON_EXPERIENCE = re.compile(
    r'"[^"\n]*\b(I|I\'ve|I\'m|my|me)\b[^"\n]*"|'
    r"“[^”\n]*\b(I|I've|I'm|my|me)\b[^”\n]*”|"
    r"\b(says|— ?[A-Z][a-z]+ [A-Z][a-z]+,)\b",
)
_RESULTS_CLAIM = re.compile(
    r"\b(sav(?:e|es|ed|ing)\s+(?:\w+\s+){0,3}?(?:hours?|minutes?|days?|\$\s?\d)|"
    r"(?:cut|reduc\w+|increas\w+|boost\w+)\s+(?:\w+\s+){0,4}?(?:by\s+)?\d+(?:\.\d+)?\s*%)\b",
    re.I,
)


class ComplianceProfile(BaseModel):
    verified_on: str = ""  # ISO date the ruleset was last confirmed
    review_cadence_days: int = 90
    ai_disclosure_required: bool = True  # conservative default
    ai_disclosure_markers: list[str] = Field(
        default_factory=lambda: ["AI-generated", "AI-assisted", "created with AI"]
    )
    material_connection_markers: list[str] = Field(
        default_factory=lambda: ["affiliate", "we may earn", "paid partnership", "#ad"]
    )
    typical_results_markers: list[str] = Field(
        default_factory=lambda: ["results vary", "typical results", "not typical"]
    )
    banned_phrases: list[str] = Field(
        default_factory=lambda: ["guaranteed results", "risk-free", "no risk"]
    )
    regulated_reviewers: dict[str, str] = Field(default_factory=dict)  # vertical→human


class ComplianceProfileError(RuntimeError):
    """Malformed or EXPIRED compliance profile. Fails closed."""


class DisclosureFinding(BaseModel):
    rule: str
    message: str
    hard_fail: bool = False


def load_compliance_profile(
    mas_dir: str | pathlib.Path, *, today: dt.date | None = None
) -> ComplianceProfile:
    """Load the profile; absent file means the conservative shipped defaults.
    A profile past its review cadence fails closed rather than passing on
    old rules."""
    path = pathlib.Path(mas_dir) / COMPLIANCE_PROFILE_FILE
    if not path.exists():
        return ComplianceProfile()
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ComplianceProfileError(f"{COMPLIANCE_PROFILE_FILE}: {exc}") from exc
    try:
        profile = ComplianceProfile(**raw)
    except ValueError as exc:
        raise ComplianceProfileError(f"{COMPLIANCE_PROFILE_FILE}: {exc}") from exc
    if not profile.verified_on:
        raise ComplianceProfileError(
            f"{COMPLIANCE_PROFILE_FILE} lacks verified_on — a ruleset nobody "
            "confirmed certifies nothing"
        )
    today = today or dt.date.today()
    verified = dt.date.fromisoformat(profile.verified_on)
    if today > verified + dt.timedelta(days=profile.review_cadence_days):
        raise ComplianceProfileError(
            f"{COMPLIANCE_PROFILE_FILE} expired: verified_on {profile.verified_on} "
            f"+ {profile.review_cadence_days}d cadence has passed — re-verify "
            "the ruleset (fails closed, risk R-P4)"
        )
    return profile


def disclosure_lint(
    draft: Draft,
    profile: ComplianceProfile,
    register: ReleaseContract | None = None,
) -> list[DisclosureFinding]:
    findings = []
    text_lower = draft.text.lower()

    def has_marker(markers: list[str]) -> bool:
        return any(m.lower() in text_lower for m in markers)

    # Endorsement / testimonial / first-person experience — the hard row.
    if _FIRST_PERSON_EXPERIENCE.search(draft.text):
        endorser = draft.endorser
        if (
            endorser is None
            or not endorser.material_connection_disclosed
            or not endorser.artifact_locator
        ):
            findings.append(
                DisclosureFinding(
                    rule="endorsement_without_endorser",
                    message="first-person experience/testimonial prose with no "
                    "real, identified endorser and recorded material-connection "
                    "disclosure (16 CFR Part 255; fabricated reviews are per-se "
                    "deceptive)",
                    hard_fail=True,
                )
            )

    if (
        draft.ai_generated
        and draft.advertising
        and profile.ai_disclosure_required
        and not has_marker(profile.ai_disclosure_markers)
    ):
        findings.append(
            DisclosureFinding(
                rule="missing_ai_disclosure",
                message="substantially AI-generated advertising lacks an "
                "AI-involvement disclosure in the content itself",
            )
        )

    if draft.affiliate and not has_marker(profile.material_connection_markers):
        findings.append(
            DisclosureFinding(
                rule="missing_material_connection",
                message="affiliate/paid relationship without a material-"
                "connection disclosure in the content (link-in-bio is not "
                "disclosure)",
            )
        )

    if _RESULTS_CLAIM.search(draft.text) and not has_marker(
        profile.typical_results_markers
    ):
        typical_basis = register is not None and any(
            c.typical_results for c in register.claims_available
        )
        if not typical_basis:
            findings.append(
                DisclosureFinding(
                    rule="atypical_results_unqualified",
                    message="results/outcome claim without a typical-results "
                    "basis in the register or a typical-results qualifier",
                )
            )

    if draft.regulated_vertical:
        reviewer = profile.regulated_reviewers.get(draft.regulated_vertical, "")
        if not reviewer:
            findings.append(
                DisclosureFinding(
                    rule="regulated_review_unrouted",
                    message=f"vertical {draft.regulated_vertical!r} was flagged at "
                    "Gate PL1 but the compliance profile names no human reviewer "
                    "for it",
                    hard_fail=True,
                )
            )
    return findings
