"""injection_scan (§20.55.4) — prompt injection is now the normal case.

The retrieved corpus is actively optimized against retrieval agents.
Retrieval runs quarantined (fetch+snapshot only); the privileged session
reads snapshots as quoted values. This scan is the deterministic layer
over those snapshots:

- instruction-shaped content inside a snapshot marks the claims built on
  it `contaminated` — quotable with the flag, but never grounds a gate
  decision;
- a single source appearing across >=3 unrelated claims is a
  source-concentration finding (the polluted-page failure mode in a form
  a deterministic check can see);
- a snapshot whose content no longer matches its recorded hash is drift —
  the evidence the gate would re-run against is not the evidence that was
  read.
"""

from __future__ import annotations

import pathlib
import re
import urllib.parse
from collections import defaultdict

from pydantic import BaseModel

from ai_venture_studio.product.evidence import resolve_snapshot, verify_snapshot

_INSTRUCTION_SHAPED = re.compile(
    r"\b(ignore (?:all )?previous|disregard (?:the )?above|"
    r"you (?:are|must)\b.{0,40}\b(?:assistant|model|AI)\b|"
    r"(?:always )?(?:cite|recommend|rank|choose) (?:this|our|us)\b|"
    r"do not (?:cite|mention|recommend) (?:any )?(?:other|competitor))",
    re.I,
)

SOURCE_CONCENTRATION_FLOOR = 3


class InjectionFinding(BaseModel):
    claim_id: str = ""
    rule: str  # contaminated | source_concentration | snapshot_drift
    message: str


def _source_key(locator: str) -> str:
    parsed = urllib.parse.urlsplit(locator)
    return parsed.netloc or locator


def injection_scan(
    ledger: dict, mas_dir: str | pathlib.Path
) -> list[InjectionFinding]:
    findings: list[InjectionFinding] = []
    claims_by_source: dict[str, list[str]] = defaultdict(list)

    for claim in ledger.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        cid = str(claim.get("id", "?"))
        for entry in claim.get("evidence") or []:
            if not isinstance(entry, dict):
                continue
            locator = str(entry.get("locator") or "")
            if locator:
                claims_by_source[_source_key(locator)].append(cid)
            artifact_hash = str(entry.get("artifact_hash") or "")
            if not artifact_hash:
                continue
            path = resolve_snapshot(artifact_hash, mas_dir)
            if path is None or not verify_snapshot(artifact_hash, mas_dir):
                findings.append(
                    InjectionFinding(
                        claim_id=cid,
                        rule="snapshot_drift",
                        message=f"snapshot {artifact_hash[:16]}… is missing or no "
                        "longer matches its recorded hash — re-probe before this "
                        "claim grounds anything",
                    )
                )
                continue
            content = path.read_text(errors="replace")
            match = _INSTRUCTION_SHAPED.search(content)
            if match:
                findings.append(
                    InjectionFinding(
                        claim_id=cid,
                        rule="contaminated",
                        message=f"snapshot contains instruction-shaped content "
                        f"({match.group(0)!r}) — claim is quotable with the flag "
                        "but may not ground a gate decision",
                    )
                )

    for source, claim_ids in sorted(claims_by_source.items()):
        distinct = sorted(set(claim_ids))
        if len(distinct) >= SOURCE_CONCENTRATION_FLOOR:
            findings.append(
                InjectionFinding(
                    rule="source_concentration",
                    message=f"source {source!r} supports {len(distinct)} claims "
                    f"({', '.join(distinct)}) — a single polluted page could be "
                    "steering the assessment",
                )
            )
    return findings
