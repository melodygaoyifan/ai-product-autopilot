"""signal_router (§22.62.1) — the P4 / Stage 8 split, machine-checked.

The routing rule is one line: a signal is Stage 8's if it indicates the
system behaved other than as specified; it is P4's if the system behaved
as specified and the OUTCOME is unsatisfactory. Ambiguous signals go to
Stage 8 first — a wrong routing toward the faster loop is cheap, and the
reverse is not. Unclassifiable signals escalate rather than being guessed
at (conservative-by-default, mode_router's posture, §11.20).
"""

from __future__ import annotations

from pydantic import BaseModel

# The system behaved other than as specified → Stage 8 Maintenance.
STAGE8_CLASSES = frozenset(
    {
        "error",
        "exception",
        "latency",
        "saturation",
        "availability",
        "crash",
        "timeout",
        "security_alert",
        "data_loss",
    }
)

# The system behaved as specified; the outcome is unsatisfactory → P4.
P4_CLASSES = frozenset(
    {
        "activation",
        "retention",
        "funnel",
        "feature_adoption",
        "feedback_text",
        "churn_reason",
        "channel_health",
        "conversion",
        "nps",
    }
)

# Could be either (a complaint spike may be an outage or a product failure).
# Stage 8 first: the faster loop triages cheaply and hands product-shaped
# residue back.
AMBIGUOUS_CLASSES = frozenset({"complaint_spike", "support_volume", "refund_spike"})


class Signal(BaseModel):
    id: str
    cls: str
    description: str = ""


class Routing(BaseModel):
    signal_id: str
    destination: str  # stage8 | p4 | escalate
    reason: str


def route_signal(signal: Signal) -> Routing:
    cls = signal.cls.strip().lower()
    if cls in STAGE8_CLASSES:
        return Routing(
            signal_id=signal.id,
            destination="stage8",
            reason=f"{cls}: system behaved other than as specified",
        )
    if cls in P4_CLASSES:
        return Routing(
            signal_id=signal.id,
            destination="p4",
            reason=f"{cls}: system as specified, outcome unsatisfactory",
        )
    if cls in AMBIGUOUS_CLASSES:
        return Routing(
            signal_id=signal.id,
            destination="stage8",
            reason=f"{cls}: ambiguous — Stage 8 first, wrong routing toward "
            "the faster loop is cheap",
        )
    return Routing(
        signal_id=signal.id,
        destination="escalate",
        reason=f"unclassifiable signal class {signal.cls!r} — escalating "
        "rather than guessing",
    )
