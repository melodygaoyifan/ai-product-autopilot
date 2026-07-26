"""Shared P3 artifact models.

External facts (DNS auth state, crawler rules, trailing complaint rates)
enter these models as recorded observations, populated by availability-
gated wrappers at runtime — wrapped, never vendored (§23 Appendix N), and
hermetic under test. The checks themselves are structural and pure.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Endorser(BaseModel):
    name: str
    material_connection_disclosed: bool = False
    artifact_locator: str = ""  # must resolve to a real, identified endorser


class Draft(BaseModel):
    """Any outbound copy artifact: post, article, email body, reply."""

    id: str
    channel: str = ""
    text: str
    ai_generated: bool = True
    advertising: bool = True
    affiliate: bool = False
    endorser: Endorser | None = None
    regulated_vertical: str = ""  # set from Gate PL1 regulatory findings
    reviewer: str = ""  # named human editorial reviewer (§21.58.4)
    claim_ledger: dict = Field(default_factory=dict)  # this artifact's claims
    links: list[str] = Field(default_factory=list)


class DomainAuth(BaseModel):
    """Recorded authentication/reputation state of a sending domain."""

    spf: bool = False
    dkim: bool = False
    dmarc: bool = False
    aligned: bool = False
    age_days: int = 0
    daily_volume: int = 0
    trailing_complaint_rate: float = 0.0
    trailing_bounce_rate: float = 0.0


class Recipient(BaseModel):
    id: str
    consent_basis: str = ""  # recorded lawful basis; empty = none recorded
    provenance: str = ""  # where the address came from; empty = unknown
    suppressed: bool = False  # on the unsubscribe/complaint suppression list


class EmailArtifact(BaseModel):
    draft: Draft
    sending_domain: DomainAuth
    headers: dict[str, str] = Field(default_factory=dict)
    recipients: list[Recipient] = Field(default_factory=list)
    per_mailbox_daily: int = 0
    marketing_class: bool = True  # bulk marketing mail vs 1:1 transactional


class Page(BaseModel):
    """A publishable web page, for spam-policy and GEO checks."""

    path: str
    title: str = ""
    text: str = ""
    hidden_text: str = ""  # display:none / zero-size / off-screen content
    structured_data: list[str] = Field(default_factory=list)  # raw JSON-LD
    author_name: str = ""
    author_identity_url: str = ""
    canonical_url: str = ""
    published_at: str = ""
    modified_at: str = ""
    crawler_access: dict[str, bool] = Field(default_factory=dict)  # robots.txt
    cdn_blocks: list[str] = Field(default_factory=list)  # CDN bot rules
    intended_crawlers: list[str] = Field(default_factory=list)
    reviewer: str = ""
    claim_ledger: dict = Field(default_factory=dict)
