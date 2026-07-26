"""The P3 autonomy ceiling (§21.57) — publishing is never autonomous.

Every other stage's worst failure is internal; this stage's worst failure
is external and irreversible — a published false claim, a burned sending
domain, a banned community account. So the ceiling is inverted: the system
may do everything except press the button.

The floor below is hardcoded. Config (.mas/authoring-policy.yaml) may only
narrow autonomy relative to it; any key that would widen it — an allow
list, a remove list, a grant — fails startup with a named error. There is
no code path in this package that publishes, sends, or spends: the
strongest form of forbidden_autonomous is that the capability does not
exist (same posture as Gate R's absent submit function).

ADR-U20: the framework never spends money. No paid channel exists, no
budget field parses, no cap is configurable — a cap bounds the loss but
not the mechanism.
"""

from __future__ import annotations

import pathlib

import yaml

AUTHORING_POLICY_FILE = "authoring-policy.yaml"

# §21.57.2 — appended to the hardcoded ceiling. Loader-enforced floor.
FORBIDDEN_AUTONOMOUS = frozenset(
    {
        "publish_external",  # any post, article, page, or reply on any surface
        "send_outbound",  # any email/DM to a person, including one message
        "modify_public_property",  # site copy, pricing page, store listing
        "respond_as_brand",  # replies to reviews, community threads
        "create_or_authenticate_account",
        "spend_money",  # ADR-U20 — all budget actions, in any tier, ever
        "contact_list_construction",  # person-level outreach lists, §22.64
        "platform_submission",  # inherited unchanged from ADR-U14
    }
)

# Config keys whose only possible purpose is widening autonomy. Their
# presence — regardless of value — fails startup.
_WIDENING_KEYS = frozenset(
    {
        "allow_autonomous",
        "autonomous",
        "forbidden_autonomous_remove",
        "permit_autonomous",
        "autonomy_grants",
    }
)


class AutonomyPolicyError(RuntimeError):
    """Raised when config attempts to widen the autonomy ceiling."""


def load_forbidden_autonomous(mas_dir: str | pathlib.Path) -> frozenset[str]:
    """Load the effective forbidden_autonomous set: the floor plus any
    config additions. Config may only narrow autonomy (add entries)."""
    path = pathlib.Path(mas_dir) / AUTHORING_POLICY_FILE
    if not path.exists():
        return FORBIDDEN_AUTONOMOUS
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise AutonomyPolicyError(
            f"{AUTHORING_POLICY_FILE} is not valid YAML: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise AutonomyPolicyError(f"{AUTHORING_POLICY_FILE} must be a mapping")

    widening = _WIDENING_KEYS & set(raw)
    if widening:
        raise AutonomyPolicyError(
            f"{AUTHORING_POLICY_FILE} contains {sorted(widening)} — config may "
            "narrow autonomy, never widen it (§21.57.2); the floor includes "
            f"{sorted(FORBIDDEN_AUTONOMOUS)}"
        )

    additions = raw.get("forbidden_autonomous_add") or []
    if not isinstance(additions, list):
        raise AutonomyPolicyError("forbidden_autonomous_add must be a list")
    return FORBIDDEN_AUTONOMOUS | {str(a) for a in additions}
