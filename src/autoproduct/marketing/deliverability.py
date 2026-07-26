"""deliverability_preflight (§21.58.3) — before a human is even asked.

Placement thresholds (complaint rate, bounce, warmth, volume) are
operational hygiene: config values with a verified_on date, tunable.
Consent and suppression are legal obligations (CAN-SPAM, GDPR/PECR, CASL):
hard-coded, non-overridable, and the config schema has no field that could
disable them — a config that tries fails load with a named error. The
distinction is the design (§21.58.3 last two rows).

Threshold defaults carry the practitioner-consensus values of §21.58.3
(complaint ceiling 0.30% with 0.10% operating target, bounce 2%,
50-100/mailbox/day for cold classes) — verify at adoption, they are
config, never constants the operator cannot see.
"""

from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel

from autoproduct.marketing.artifacts import EmailArtifact

DELIVERABILITY_CONFIG_FILE = "deliverability.yaml"

# The non-overridable core. Not present in the config model at all — the
# strongest available form of "hard-coded".
_HARD_RULES = ("consent", "suppression")


class DeliverabilityConfig(BaseModel):
    verified_on: str = ""
    complaint_rate_ceiling: float = 0.003  # provider ceiling ~0.30%
    complaint_rate_target: float = 0.001  # practical operating target
    bounce_rate_ceiling: float = 0.02
    min_domain_age_days: int = 30
    warmup_daily_volume: dict[int, int] = {7: 50, 14: 200, 30: 1000}
    per_mailbox_daily_cap: int = 100


class DeliverabilityConfigError(RuntimeError):
    """Raised when config tries to touch the non-overridable rules."""


class DeliverabilityFinding(BaseModel):
    rule: str
    message: str
    hard_fail: bool = False  # consent/suppression: no override path exists


def load_deliverability_config(
    mas_dir: str | pathlib.Path,
) -> DeliverabilityConfig:
    path = pathlib.Path(mas_dir) / DELIVERABILITY_CONFIG_FILE
    if not path.exists():
        return DeliverabilityConfig()
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise DeliverabilityConfigError(f"{DELIVERABILITY_CONFIG_FILE}: {exc}") from exc
    if not isinstance(raw, dict):
        raise DeliverabilityConfigError(f"{DELIVERABILITY_CONFIG_FILE} must be a mapping")
    touched = [k for k in raw if any(h in k.lower() for h in _HARD_RULES)]
    if touched:
        raise DeliverabilityConfigError(
            f"{DELIVERABILITY_CONFIG_FILE} contains {touched} — consent and "
            "suppression checks are hard-coded and non-overridable (§21.58.3); "
            "placement thresholds are the tunable part"
        )
    try:
        return DeliverabilityConfig(**raw)
    except ValueError as exc:
        raise DeliverabilityConfigError(f"{DELIVERABILITY_CONFIG_FILE}: {exc}") from exc


def deliverability_preflight(
    email: EmailArtifact, config: DeliverabilityConfig | None = None
) -> list[DeliverabilityFinding]:
    config = config or DeliverabilityConfig()
    findings = []
    domain = email.sending_domain

    if not (domain.spf and domain.dkim and domain.dmarc and domain.aligned):
        findings.append(
            DeliverabilityFinding(
                rule="authentication",
                message="SPF, DKIM and DMARC must all be present and aligned — "
                "bulk-sender requirements are enforced, not advisory",
            )
        )

    if email.marketing_class:
        headers = {k.lower() for k in email.headers}
        if "list-unsubscribe" not in headers or "list-unsubscribe-post" not in headers:
            findings.append(
                DeliverabilityFinding(
                    rule="one_click_unsubscribe",
                    message="marketing-class mail requires List-Unsubscribe and "
                    "List-Unsubscribe-Post (RFC 8058)",
                )
            )

    if domain.trailing_complaint_rate > config.complaint_rate_ceiling:
        findings.append(
            DeliverabilityFinding(
                rule="complaint_rate",
                message=f"trailing complaint rate {domain.trailing_complaint_rate:.2%} "
                f"above configured ceiling {config.complaint_rate_ceiling:.2%}",
            )
        )
    if domain.trailing_bounce_rate > config.bounce_rate_ceiling:
        findings.append(
            DeliverabilityFinding(
                rule="bounce_rate",
                message=f"trailing bounce rate {domain.trailing_bounce_rate:.2%} "
                f"above configured ceiling {config.bounce_rate_ceiling:.2%}",
            )
        )

    ramp_cap = None
    for age, cap in sorted(config.warmup_daily_volume.items()):
        if domain.age_days <= age:
            ramp_cap = cap
            break
    if domain.age_days < config.min_domain_age_days and ramp_cap is not None:
        if domain.daily_volume > ramp_cap:
            findings.append(
                DeliverabilityFinding(
                    rule="domain_warmth",
                    message=f"domain aged {domain.age_days}d sending "
                    f"{domain.daily_volume}/day exceeds the warm-up schedule cap "
                    f"{ramp_cap} — unwarmed domains at agent volume lose placement",
                )
            )

    if email.per_mailbox_daily > config.per_mailbox_daily_cap:
        findings.append(
            DeliverabilityFinding(
                rule="per_mailbox_volume",
                message=f"{email.per_mailbox_daily}/mailbox/day above configured "
                f"cap {config.per_mailbox_daily_cap}",
            )
        )

    # --- the non-tunable rows: legal obligations, no override path ----------
    for recipient in email.recipients:
        if not recipient.consent_basis or not recipient.provenance:
            findings.append(
                DeliverabilityFinding(
                    rule="list_provenance",
                    message=f"recipient {recipient.id!r} lacks a recorded lawful "
                    "basis and provenance record (§22.64) — hard fail, no override",
                    hard_fail=True,
                )
            )
        if recipient.suppressed:
            findings.append(
                DeliverabilityFinding(
                    rule="suppression",
                    message=f"recipient {recipient.id!r} is on the unsubscribe/"
                    "complaint suppression list — hard fail, no override",
                    hard_fail=True,
                )
            )
    return findings
