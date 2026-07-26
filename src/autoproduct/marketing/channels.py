"""Channel profiles (§21.59) — deltas on P3, never forks (ADR-U12).

A profile may ADD checks, voters, gates, and forbidden actions; it may
never remove or weaken. Cadence ceilings are ceilings: every channel
carries a maximum and none carries a minimum, because a publish-rate
target handed to an optimizing agent is a scaled-content-abuse generator
with a KPI (§21.59.5). Config may lower a ceiling, never raise it above
the built-in.

There is no `paid` channel and the loader rejects one by name: the
framework does not spend money (ADR-U20) — not implemented is the
implementation.
"""

from __future__ import annotations

import copy
import pathlib

import yaml
from pydantic import BaseModel, Field

CHANNEL_PROFILE_FILE = "channel-profile.yaml"

# §21.59 — the five built-in profiles. det_tools are the core set a config
# can extend and never shrink.
BUILTIN_CHANNELS: dict[str, dict] = {
    "content_geo": {
        "det_tools": [
            "claim_substantiation_check",
            "spam_policy_check",
            "geo_extractability_check",
            "utm_and_instrumentation_lint",
        ],
        "voters": ["Extractability", "OriginalContribution"],
        "human_gate": "editorial approval, named reviewer recorded",
        "cadence": {"max_publishes_per_week": 2},
    },
    "email": {
        "det_tools": [
            "claim_substantiation_check",
            "disclosure_lint",
            "deliverability_preflight",
            "utm_and_instrumentation_lint",
        ],
        "voters": ["Consent-Basis", "Relevance"],
        "human_gate": "send approval per campaign, batch-scoped",
        "cadence": {"max_sends_per_week": 1},
    },
    "community": {
        "det_tools": [
            "claim_substantiation_check",
            "disclosure_lint",
            "brand_and_safety_scan",
        ],
        "voters": ["Norm-Fit", "Value-First"],
        "human_gate": "post approval, per post",
        "cadence": {"max_posts_per_week": 3},
        "rules": [
            "official API only; browser automation forbidden",
            "self-promotion ratio tracked; mostly-self-promo accounts are a "
            "policy violation and a strategy failure",
        ],
    },
    "social": {
        "det_tools": [
            "claim_substantiation_check",
            "disclosure_lint",
            "brand_and_safety_scan",
        ],
        "voters": ["Voice", "Disclosure"],
        "human_gate": "post approval, per post or per homogeneous batch",
        "cadence": {"max_posts_per_week": 5},
        "rules": ["no synthetic persona accounts, ever"],
    },
    "product_surface": {
        "det_tools": ["claim_substantiation_check", "brand_and_safety_scan"],
        "voters": ["Clarity", "Accuracy"],
        "human_gate": "rides the normal inner-loop PR gates — it is code, "
        "reviewed as code",
        "cadence": {},
    },
}


class ChannelProfileError(RuntimeError):
    """Raised when a channel config removes/weakens a core check, raises a
    cadence ceiling, or declares a paid channel."""


class ChannelProfile(BaseModel):
    id: str
    det_tools: list[str]
    voters: list[str]
    human_gate: str
    cadence: dict[str, int] = Field(default_factory=dict)
    rules: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=list)
    forbidden_autonomous_add: list[str] = Field(default_factory=list)


def load_channel_profiles(
    mas_dir: str | pathlib.Path,
) -> dict[str, ChannelProfile]:
    """Built-in five, tightened (never weakened) by .mas/channel-profile.yaml."""
    merged = copy.deepcopy(BUILTIN_CHANNELS)
    path = pathlib.Path(mas_dir) / CHANNEL_PROFILE_FILE
    overrides: dict[str, dict] = {}
    if path.exists():
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as exc:
            raise ChannelProfileError(f"{CHANNEL_PROFILE_FILE}: {exc}") from exc
        for entry in raw.get("channels") or []:
            if not isinstance(entry, dict) or not entry.get("id"):
                raise ChannelProfileError(f"channel entry lacks an id: {entry!r}")
            overrides[str(entry["id"])] = entry

    for channel_id, entry in overrides.items():
        if channel_id == "paid" or entry.get("kind") == "paid":
            raise ChannelProfileError(
                "channel 'paid' is not implemented and cannot be configured — "
                "the framework does not spend money (ADR-U20)"
            )
        base = merged.get(channel_id)
        if base is None:
            # New channels start from the strictest posture: all seven backstops.
            merged[channel_id] = {
                "det_tools": sorted(
                    {t for c in BUILTIN_CHANNELS.values() for t in c["det_tools"]}
                ),
                "voters": list(entry.get("voter_deltas") or []),
                "human_gate": "post approval, per post",
                "cadence": dict(entry.get("cadence") or {}),
                "rules": list(entry.get("rules") or []),
            }
            continue
        if "det_tools" in entry or "voters" in entry:
            raise ChannelProfileError(
                f"{channel_id}: config sets det_tools/voters directly — a profile "
                "may only add via det_tools_add/voter_deltas, never redefine the "
                "core set"
            )
        base["det_tools"] = [
            *base["det_tools"],
            *[
                t
                for t in entry.get("det_tools_add") or []
                if t not in base["det_tools"]
            ],
        ]
        base["voters"] = [
            *base["voters"],
            *[v for v in entry.get("voter_deltas") or [] if v not in base["voters"]],
        ]
        for key, value in (entry.get("cadence") or {}).items():
            built_in = base["cadence"].get(key)
            if built_in is not None and int(value) > built_in:
                raise ChannelProfileError(
                    f"{channel_id}: cadence {key}={value} raises the built-in "
                    f"ceiling {built_in} — ceilings may be lowered, never raised"
                )
            base["cadence"][key] = int(value)
        base.setdefault("rules", []).extend(entry.get("rules") or [])
        base["surfaces"] = list(entry.get("surfaces") or [])
        base["forbidden_autonomous_add"] = list(
            entry.get("forbidden_autonomous_add") or []
        )

    return {
        cid: ChannelProfile(id=cid, **spec) for cid, spec in merged.items()
    }
