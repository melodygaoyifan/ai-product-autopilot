"""claim_lint (§20.53.3) — structural validation of P-stage claim ledgers.

Deterministic, no model calls. Mirrors ears_lint's contract: the outer
loop's artifacts are made machine-checkable, then the gate runs the check.
Runs before any voter sees the artifact (ADR-U05); findings block the
stage gate with no degraded mode.

Five rules each kill a specific observed failure mode:
- unsourced_number            — the invented TAM
- causal_without_experiment   — "our launch post drove 40% of signups"
- no_denominator              — "3 of 5 vendors" with no n
- no_falsifier                — a claim with no falsifier is a slogan
- stale                       — four-month-old pricing is not evidence about today
"""

from __future__ import annotations

import datetime as dt
import re

from pydantic import BaseModel

from autoproduct.product.claims import SOURCE_TYPES, ProductPolicy

_CAUSAL = re.compile(r"\b(drove|caused|because of|led to|resulted in|due to)\b", re.I)
_QUANT = re.compile(
    r"(\d+(?:\.\d+)?\s*%|\$\s?\d|\b\d+(?:\.\d+)?\s*(?:x|×)\b|\bCAGR\b|\bTAM\b|\bSAM\b|\bSOM\b)"
)
_VAGUE = re.compile(
    r"\b(most|many|significant|substantial|leading|rapidly|huge|massive)\b", re.I
)
_PROPORTION = re.compile(r"\b\d+\s+of\s+\d+\b|\brate\b|\bshare\b", re.I)

# External citations must be snapshotted (§20.53.5); our own measurements
# and stored user artifacts are already inside the boundary.
_SNAPSHOT_REQUIRED = {"primary_cited", "third_party_report"}


class ClaimIssue(BaseModel):
    claim_id: str = ""  # empty for ledger-level findings
    rule: str
    message: str


def _check_claim(c: dict, today: dt.date) -> list[ClaimIssue]:
    issues: list[ClaimIssue] = []
    cid = str(c.get("id", "?"))
    st = c.get("source_type")

    def issue(rule: str, message: str) -> None:
        issues.append(ClaimIssue(claim_id=cid, rule=rule, message=message))

    if st not in SOURCE_TYPES:
        issue("bad_source_type", f"{st!r} not in {sorted(SOURCE_TYPES)}")
        return issues

    if st != "model_inference":
        evidence = c.get("evidence") or []
        if not evidence:
            issue("unsourced", f"{st} requires >=1 evidence entry")
        for entry in evidence:
            if not isinstance(entry, dict):
                issue("unsourced", "evidence entry is not a mapping")
                continue
            if not entry.get("locator"):
                issue("no_locator", "evidence lacks a reproducible locator")
            if not entry.get("retrieved_at"):
                issue("no_retrieval_time", "evidence lacks retrieved_at")
            if st in _SNAPSHOT_REQUIRED and not entry.get("artifact_hash"):
                issue(
                    "no_snapshot",
                    "cited external evidence must be snapshotted (§20.53.5)",
                )

    text = str(c.get("text", ""))
    if _QUANT.search(text) and st == "model_inference":
        issue("unsourced_number", "quantitative claim may not be model_inference")
    if _CAUSAL.search(text) and st != "primary_measured":
        issue(
            "causal_without_experiment",
            "causal language requires primary_measured (holdout/experiment) — §22.63",
        )
    vague = _VAGUE.search(text)
    if vague and not _QUANT.search(text):
        issue(
            "unquantified",
            f"vague quantifier {vague.group(0)!r} with no number — "
            "the claim-layer 'fast'",
        )
    if _PROPORTION.search(text) and not c.get("n"):
        issue("no_denominator", "proportion claim without n")
    if not c.get("falsifier"):
        issue("no_falsifier", "claim states no disconfirming observation")

    expires = c.get("expires")
    if expires:
        try:
            expiry = dt.date.fromisoformat(str(expires))
        except ValueError:
            issue("stale", f"expires {expires!r} is not an ISO date")
        else:
            if expiry < today:
                issue("stale", f"evidence expired {expires}; re-probe or downgrade")
    return issues


def lint_ledger(
    doc: dict,
    artifact_kind: str,
    *,
    today: dt.date | None = None,
    policy: ProductPolicy | None = None,
) -> list[ClaimIssue]:
    """Lint one claim ledger. Empty result means the gate may proceed."""
    today = today or dt.date.today()
    policy = policy or ProductPolicy()
    claims = doc.get("claims") or []
    if not claims:
        return [ClaimIssue(rule="empty_ledger", message="artifact has no claim ledger")]

    issues: list[ClaimIssue] = []
    inferred = 0
    for c in claims:
        if not isinstance(c, dict):
            issues.append(
                ClaimIssue(rule="malformed_claim", message=f"claim is not a mapping: {c!r}")
            )
            continue
        if c.get("source_type") == "model_inference":
            inferred += 1
        issues.extend(_check_claim(c, today))

    ratio = inferred / len(claims)
    ceiling = policy.ceiling_for(artifact_kind)
    if ratio > ceiling:
        issues.append(
            ClaimIssue(
                rule="inference_ratio",
                message=(
                    f"model_inference {ratio:.0%} > ceiling {ceiling:.0%} "
                    f"for kind={artifact_kind}"
                ),
            )
        )
    return issues
