"""Attestation ledger — the local-integrity half (§18.49 item 2, §19 G15-16).

Append-only, hash-chained JSONL over the gate/verdict/override records the
YAML mirror already holds. Each entry commits to its predecessor
(sha256 over canonical JSON), so edits, deletions, and reordering anywhere
in history break verification from that point on.

Scope honesty: this chain proves INTEGRITY (the trail wasn't altered after
writing), not AUTHORSHIP. Org-key signing — proving *who* attested — is
the deferred half; it needs the adopting org's key decision (G15's external
dependency) and slots in as a signature field per entry without changing
this format.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

LEDGER_PATH = ".mas/attestation/ledger.jsonl"

_GENESIS = "0" * 64


class LedgerEntry(BaseModel):
    seq: int
    written_at: str
    payload: dict
    prev_hash: str
    entry_hash: str


class LedgerVerification(BaseModel):
    ok: bool
    entries: int
    first_bad_seq: int | None = None
    problems: list[str] = Field(default_factory=list)


def _hash_entry(seq: int, written_at: str, payload: dict, prev_hash: str) -> str:
    canonical = json.dumps(
        {"seq": seq, "written_at": written_at, "payload": payload,
         "prev_hash": prev_hash},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_ledger(path: Path) -> list[LedgerEntry]:
    if not path.exists():
        return []
    entries = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            entries.append(LedgerEntry(**json.loads(line)))
        except Exception as exc:
            raise ValueError(f"{path}:{i + 1}: unreadable ledger line — {exc}") from exc
    return entries


def append_attestation(repo_dir: str | Path, payload: dict) -> LedgerEntry:
    if not payload:
        raise ValueError("refusing to attest an empty payload")
    path = Path(repo_dir) / LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_ledger(path)
    prev_hash = existing[-1].entry_hash if existing else _GENESIS
    seq = existing[-1].seq + 1 if existing else 1
    written_at = datetime.datetime.now(datetime.UTC).isoformat()
    entry = LedgerEntry(
        seq=seq, written_at=written_at, payload=payload, prev_hash=prev_hash,
        entry_hash=_hash_entry(seq, written_at, payload, prev_hash),
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry.model_dump(), ensure_ascii=False) + "\n")
    return entry


def verify_ledger(repo_dir: str | Path) -> LedgerVerification:
    """Recompute the whole chain. An empty ledger verifies (there is nothing
    to have tampered with) but reports entries=0 so it never reads as
    attested history."""
    entries = _read_ledger(Path(repo_dir) / LEDGER_PATH)
    problems = []
    first_bad = None
    prev_hash = _GENESIS
    for i, entry in enumerate(entries):
        expected_seq = i + 1
        recomputed = _hash_entry(entry.seq, entry.written_at, entry.payload, entry.prev_hash)
        for cond, msg in (
            (entry.seq != expected_seq, f"seq {entry.seq} != expected {expected_seq} (removal/reorder)"),
            (entry.prev_hash != prev_hash, f"seq {entry.seq}: broken chain link"),
            (entry.entry_hash != recomputed, f"seq {entry.seq}: content altered after writing"),
        ):
            if cond:
                problems.append(msg)
                if first_bad is None:
                    first_bad = entry.seq
        prev_hash = entry.entry_hash
    return LedgerVerification(
        ok=not problems, entries=len(entries),
        first_bad_seq=first_bad, problems=problems,
    )


def attest_review(repo_dir: str | Path, review_id: str) -> int:
    """Append every gate/verdict/override mark of one review's mirror to
    the ledger. Idempotence by construction: re-attesting the same review
    appends duplicate payloads rather than editing history — the ledger
    records that it happened twice, which is the point."""
    from ai_venture_studio.adoption.evidence import attestable_marks

    marks = attestable_marks(Path(repo_dir), review_id)
    if not marks:
        raise ValueError(
            f"review {review_id} has no gate/verdict state to attest"
        )
    for mark in marks:
        append_attestation(repo_dir, {"review_id": review_id, **mark})
    return len(marks)


def review_attested(repo_dir: str | Path, review_id: str) -> bool:
    verification = verify_ledger(repo_dir)
    if not verification.ok or verification.entries == 0:
        return False
    entries = _read_ledger(Path(repo_dir) / LEDGER_PATH)
    return any(e.payload.get("review_id") == review_id for e in entries)
