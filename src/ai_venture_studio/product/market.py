"""P1 Market & Viability — competitor probes and Gate PL1 (§20.55).

Competitor facts are probes, not recollections. Two entry points:
`record_probe` does the bookkeeping for a fetch that already happened
(standing check, snapshot, hash, evidence entry), and `fetch_probe` performs
the fetch — a human-invoked, read-only GET restricted to locators that a
declared source in `.mas/signal-sources.yaml` already granted standing for.
A competitor claim with no probe hash is model_inference by definition and
counts against the 30% market ceiling.

Quarantine is structural, not advisory (ADR-U21, CaMeL): `fetch_probe`
snapshots bytes to the evidence store and returns a ledger entry. It never
returns content into a privileged session, and no agent can call it — the
operator runs `avs probe`, the bytes land on disk, and a later stage reads
them as a quoted, injection-scanned snapshot.

Gate PL1 is human, with a rubric; this module enforces its deterministic
entry conditions and records the outcome. The most common correct outcome
is `test_first` — measure before you build.
"""

from __future__ import annotations

import datetime as dt
import pathlib

from pydantic import BaseModel, Field, field_validator

from ai_venture_studio.product.claim_lint import lint_ledger
from ai_venture_studio.product.claims import ProductPolicy
from ai_venture_studio.product.evidence import store_snapshot
from ai_venture_studio.product.injection import (
    InjectionFinding,
    injection_scan,
    scan_text,
)
from ai_venture_studio.product.sizing import SizingResult
from ai_venture_studio.product.sources import (
    SignalSource,
    SignalSourceError,
    source_standing_check,
)

GATE_PL1_RUBRIC = (
    "Is the size range built bottom-up from factors I can each check?",
    "What is the strongest disconfirming finding, and is the answer evidence "
    "or narrative?",
    "Which factors are model_inference, and does the decision survive their "
    "sensitivity range?",
    "Does any regulatory finding change the shape of what we'd build?",
    "What is the cheapest test that would move me, and why aren't we running "
    "it first?",
)


def record_probe(
    content: bytes,
    *,
    locator: str,
    retrieved_at: str,
    sources: list[SignalSource],
    mas_dir: str | pathlib.Path,
    method: str = "competitor_probe",
) -> dict:
    """Snapshot a probe result and return the ledger-ready evidence entry.
    Refuses locators with no declared standing — probing where nobody
    granted access is not evidence gathering (§20.55.3)."""
    probe_doc = {"claims": [{"id": "_probe", "evidence": [{"locator": locator}]}]}
    if source_standing_check(probe_doc, sources):
        raise SignalSourceError(
            f"probe target {locator!r} matches no declared source — no standing, "
            "no probe (§20.55.3 hard boundary)"
        )
    snapshot = store_snapshot(content, mas_dir)
    return {
        "method": method,
        "locator": locator,
        "retrieved_at": retrieved_at,
        "artifact_hash": snapshot.artifact_hash,
    }


# Quarantined fetch (§20.55.3, ADR-U21). Deliberately narrow: no credentials,
# no POST, no redirect off the allowlisted host, no JS, no crawl. A probe
# reads one public page that a declared source already granted standing for.
PROBE_TIMEOUT_S = 20.0
PROBE_MAX_BYTES = 2_000_000
_PROBE_CONTENT_TYPES = ("text/html", "text/plain", "application/json",
                        "application/xhtml+xml", "text/markdown")


class ProbeFetchError(RuntimeError):
    """The fetch could not be performed within the probe contract."""


def fetch_probe(
    url: str,
    *,
    sources: list[SignalSource],
    mas_dir: str | pathlib.Path,
    method: str = "competitor_probe",
    timeout_s: float = PROBE_TIMEOUT_S,
    opener=None,
) -> tuple[dict, list[InjectionFinding]]:
    """Fetch one public page and record it as a probe.

    Returns (evidence_entry, injection_findings). The bytes go to the
    evidence store; the caller gets a hash and a locator, never the content —
    that is what makes this quarantined rather than merely careful. Findings
    from the injection scan are returned so the operator sees a page that
    tried to talk to a model instead of describing a product.

    Standing is checked before the socket opens: probing where nobody granted
    access is not evidence gathering. `http` is refused outright — a probe
    that could be rewritten in flight is not evidence.
    """
    import urllib.error
    import urllib.request

    if not url.startswith("https://"):
        raise ProbeFetchError(
            f"probe target {url!r} must be https — a plaintext fetch can be "
            "rewritten in flight, which makes the snapshot unattributable"
        )
    # Standing first: never open a connection to something undeclared.
    probe_doc = {"claims": [{"id": "_probe", "evidence": [{"locator": url}]}]}
    if source_standing_check(probe_doc, sources):
        raise SignalSourceError(
            f"probe target {url!r} matches no declared source — no standing, "
            "no probe (§20.55.3 hard boundary). Declare it in "
            ".mas/signal-sources.yaml first, with its standing recorded."
        )

    request = urllib.request.Request(  # noqa: S310 — https enforced above
        url,
        headers={
            "Accept": ", ".join(_PROBE_CONTENT_TYPES),
            # Identify honestly: a probe that hides what it is would be the
            # cloaking ADR-U21 forbids, pointed the other way.
            "User-Agent": "ai-venture-studio-probe/1 (+operator-invoked)",
        },
        method="GET",
    )
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=timeout_s) as response:  # noqa: S310
            final_url = getattr(response, "url", url) or url
            if not str(final_url).startswith("https://"):
                raise ProbeFetchError(
                    f"probe was redirected off https to {final_url!r} — refused"
                )
            # A redirect must not smuggle the probe to an undeclared host.
            redirected = {"claims": [{"id": "_probe",
                                      "evidence": [{"locator": str(final_url)}]}]}
            if source_standing_check(redirected, sources):
                raise SignalSourceError(
                    f"probe redirected to {final_url!r}, which matches no "
                    "declared source — refused rather than followed"
                )
            content_type = (response.headers.get("Content-Type") or "").lower()
            if content_type and not any(
                content_type.startswith(t) for t in _PROBE_CONTENT_TYPES
            ):
                raise ProbeFetchError(
                    f"probe target returned {content_type!r}; a probe reads "
                    f"text, not binaries ({', '.join(_PROBE_CONTENT_TYPES)})"
                )
            content = response.read(PROBE_MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        # Availability-gated: an unreachable target is a visible failure, not
        # an empty probe that would read as "checked and found nothing".
        raise ProbeFetchError(f"probe of {url!r} failed: {exc}") from exc

    if len(content) > PROBE_MAX_BYTES:
        raise ProbeFetchError(
            f"probe target exceeds {PROBE_MAX_BYTES} bytes — narrow the locator"
        )

    entry = record_probe(
        content,
        locator=url,
        retrieved_at=dt.datetime.now(dt.UTC).isoformat(),
        sources=sources,
        mas_dir=mas_dir,
        method=method,
    )
    findings = scan_text(
        content.decode("utf-8", errors="replace"), locator=url
    )
    return entry, findings


class GatePL1Entry(BaseModel):
    passed: bool
    findings: list[str]
    injection_findings: list[InjectionFinding] = Field(default_factory=list)


class GatePL1Decision(BaseModel):
    outcome: str  # pursue | test_first | park | reject
    decider: str  # a named human — forbidden_autonomous, always
    scope_tier: str = ""  # required for pursue
    named_test: str = ""  # required for test_first
    park_reason: str = ""  # required for park; routes to the kill registry

    @field_validator("decider")
    @classmethod
    def _named_human(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Gate PL1 is human, always (§21.57.2)")
        return value

    @field_validator("outcome")
    @classmethod
    def _legal(cls, value: str) -> str:
        if value not in {"pursue", "test_first", "park", "reject"}:
            raise ValueError("outcome is pursue | test_first | park | reject")
        return value

    def validate_completeness(self) -> None:
        if self.outcome == "pursue" and self.scope_tier not in {
            "thin",
            "standard",
            "deep",
        }:
            raise ValueError("pursue requires a scope_tier (thin|standard|deep)")
        if self.outcome == "test_first" and not self.named_test.strip():
            raise ValueError("test_first requires the named cheapest test")
        if self.outcome == "park" and not self.park_reason.strip():
            raise ValueError("park requires a reason — it becomes registry history")


def gate_pl1_entry(
    market_ledger: dict,
    sizing: SizingResult,
    *,
    mas_dir: str | pathlib.Path,
    disconfirmation_answered: bool,
    regulatory_triaged: bool,
    today: dt.date | None = None,
    policy: ProductPolicy | None = None,
) -> GatePL1Entry:
    """The deterministic preconditions of §20.55.5. The rubric and the
    decision stay human; contaminated claims cannot ground entry."""
    findings: list[str] = []
    for issue in lint_ledger(market_ledger, "market", today=today, policy=policy):
        findings.append(f"claim_lint:{issue.rule}: {issue.message}")
    if sizing.status != "ok" or sizing.result_range is None:
        findings.append("sizing: no bottom-up range with sensitivities")
    injection = injection_scan(market_ledger, mas_dir)
    for finding in injection:
        if finding.rule in ("contaminated", "snapshot_drift"):
            findings.append(f"injection:{finding.rule}: claim {finding.claim_id}")
    if not disconfirmation_answered:
        findings.append(
            "disconfirmation findings not answered — answered ≠ dismissed"
        )
    if not regulatory_triaged:
        findings.append("regulatory findings not triaged")
    return GatePL1Entry(
        passed=not findings, findings=findings, injection_findings=injection
    )
