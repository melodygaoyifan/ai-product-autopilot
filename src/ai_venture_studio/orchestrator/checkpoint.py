"""Shared checkpointer construction (doc 09 §3.1 / §6, plan D15+D16).

Every checkpointed graph — code review, deploy review, maintenance —
persists super-steps to the same `.mas/checkpoints.db` through this
helper, with per-stage thread-id namespaces (`<id>`, `deploy:<id>`,
`incident:<id>`).

Encryption at rest: when `AUTOPRODUCT_CHECKPOINT_KEY` is set, checkpoint
rows are encrypted via LangGraph's `EncryptedSerializer` (AES through
pycryptodome, an availability-gated optional). The key may be given
directly or as a `secret://ENV_NAME` reference through the v0.31 secrets
layer. The YAML mirror stays deliberately plaintext — it is the
human-readable audit surface (§09.6 asymmetry: in-flight intermediate
state lives only in the encrypted rows).

Failure posture: a key that cannot be honored is an error, never a
silent plaintext fallback — a checkpoint the operator believes is
encrypted but isn't would be the worst kind of quiet degradation. The
absence of a key is fine and visible: `encryption_status()` is stamped
into every run's meta.yaml.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

KEY_ENV = "AUTOPRODUCT_CHECKPOINT_KEY"


class CheckpointKeyError(RuntimeError):
    """A checkpoint key was provided but cannot be honored — fail closed."""


def _key_bytes() -> bytes | None:
    raw = os.environ.get(KEY_ENV, "").strip()
    if not raw:
        return None
    if raw.startswith("secret://"):
        from ai_venture_studio.secrets import SecretsLoader

        raw = SecretsLoader().resolve(raw).reveal()
    key = raw.encode("utf-8")
    if len(key) not in (16, 24, 32):
        # Any passphrase is accepted; derive a fixed-width key from it
        # deterministically rather than bouncing the operator on length.
        key = hashlib.sha256(key).digest()
    return key


def encryption_status() -> str:
    """'aes' | 'off' — stamped into run meta.yaml so the state of at-rest
    encryption is always inspectable after the fact."""
    return "aes" if os.environ.get(KEY_ENV, "").strip() else "off"


def build_saver(repo_dir: str | Path) -> SqliteSaver:
    """The one SqliteSaver every stage graph checkpoints through."""
    db = Path(repo_dir) / ".mas" / "checkpoints.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, check_same_thread=False)
    key = _key_bytes()
    if key is None:
        return SqliteSaver(conn)
    try:
        from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
    except ImportError as exc:
        raise CheckpointKeyError(
            f"{KEY_ENV} is set but pycryptodome is not installed — refusing "
            "to write plaintext checkpoints the operator believes are "
            "encrypted. `uv add pycryptodome` or unset the key."
        ) from exc
    return SqliteSaver(conn, serde=EncryptedSerializer.from_pycryptodome_aes(key=key))
