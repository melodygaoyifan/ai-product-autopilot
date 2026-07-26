"""Evidence snapshots (§20.53.5) — content-addressed, hashed at retrieval.

Three purposes: reproducibility (a gate that cannot be re-run against the
same inputs is theater), rot detection (a silently-changed competitor
pricing page is a finding, not a surprise), and injection forensics (when
a claim turns out to have been planted, the snapshot is what lets the
incident→fixture loop learn the pattern rather than the instance).

Snapshots inherit research_taint (§16.40.2): retrieved content enters claim
ledgers as quoted, hashed data and never reaches a code-writing context.
"""

from __future__ import annotations

import hashlib
import pathlib

from pydantic import BaseModel

EVIDENCE_DIR = "evidence"  # under .mas/


class Snapshot(BaseModel):
    artifact_hash: str  # "sha256:<hex>"
    path: str


def _evidence_root(mas_dir: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(mas_dir) / EVIDENCE_DIR


def store_snapshot(
    content: bytes, mas_dir: str | pathlib.Path, *, suffix: str = ".html"
) -> Snapshot:
    """Write retrieved content to .mas/evidence/<sha256><suffix>."""
    digest = hashlib.sha256(content).hexdigest()
    root = _evidence_root(mas_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{digest}{suffix}"
    if not path.exists():
        path.write_bytes(content)
    return Snapshot(artifact_hash=f"sha256:{digest}", path=str(path))


def resolve_snapshot(
    artifact_hash: str, mas_dir: str | pathlib.Path
) -> pathlib.Path | None:
    """Find the stored snapshot for a claim's artifact_hash, if it exists."""
    digest = artifact_hash.removeprefix("sha256:")
    matches = sorted(_evidence_root(mas_dir).glob(f"{digest}*"))
    return matches[0] if matches else None


def snapshot_differs(artifact_hash: str, refetched: bytes) -> bool:
    """Rot detection: does a re-probe hash differently from the snapshot?

    True means the source changed since retrieval — a finding for the
    claim's owner (re-probe or downgrade), never something prose smooths over.
    """
    digest = artifact_hash.removeprefix("sha256:")
    return hashlib.sha256(refetched).hexdigest() != digest


def verify_snapshot(artifact_hash: str, mas_dir: str | pathlib.Path) -> bool:
    """A snapshot exists on disk and still matches its recorded hash."""
    path = resolve_snapshot(artifact_hash, mas_dir)
    if path is None:
        return False
    return not snapshot_differs(artifact_hash, path.read_bytes())
