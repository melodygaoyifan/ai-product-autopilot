"""Deterministic text similarity — k-shingle Jaccard, stdlib only.

Shared by spam_policy_check (near-duplication, §21.58.4), P0 signal
clustering (deterministic near-dup BEFORE any embedding, ADR-U05
ordering), and the kill-registry Novelty match (§20.54.3). One
implementation so the thresholds mean the same thing everywhere.
"""

from __future__ import annotations

import re

DEFAULT_K = 5


def shingles(text: str, k: int = DEFAULT_K) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    if len(words) < k:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + k]) for i in range(len(words) - k + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similarity(text_a: str, text_b: str, k: int = DEFAULT_K) -> float:
    return jaccard(shingles(text_a, k), shingles(text_b, k))
