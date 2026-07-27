#!/usr/bin/env python3
"""A tiny deterministic "game" that emits the bot-session protocol.

This exists so the fleet is verified against real sessions of a real
simulation rather than a mocked stream: `run_fleet` spawns this as a
subprocess exactly as it would spawn a Unity headless build, and the
detectors run over what it actually printed.

It is also a worked example of the protocol an engine adapter must emit:
one JSON object per line, `kind` in {tick, error, crash, goal}, with
`state_hash`, `pos`, and `reachable` on ticks.

The seed selects behaviour, so the fleet has something to find:

    seed % 5 == 0  → softlock  (walks into a corner and stops moving)
    seed % 7 == 0  → crash     (raises after a few ticks)
    seed % 11 == 0 → out of bounds (walks past the play area)
    otherwise      → a clean session that reaches its goal

Run it by hand exactly as a fleet finding says to:
    AUTOPRODUCT_BOT_SEED=5 python3 benchmarks/botfleet/toy_sim.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

TICKS = 60
BOUNDS = 10.0


def emit(**event) -> None:
    print(json.dumps(event), flush=True)


def state_hash(x: float, y: float, step: int) -> str:
    # Deterministic and position-derived: two ticks at the same place hash
    # the same, which is what makes softlock detection possible.
    return hashlib.sha256(f"{x:.2f},{y:.2f}".encode()).hexdigest()[:8]


def main() -> int:
    seed = int(os.environ.get("AUTOPRODUCT_BOT_SEED", "1"))
    profile = os.environ.get("AUTOPRODUCT_NET_PROFILE", "")
    if profile:
        emit(t=0, kind="note", message=f"net profile {profile}")

    softlock = seed % 5 == 0
    crash = seed % 7 == 0
    escape = seed % 11 == 0

    x = y = 0.0
    reachable = 12
    for step in range(TICKS):
        if crash and step == 8:
            emit(t=step, kind="crash",
                 message=f"IndexError: tile index {seed * 3} out of range")
            return 1
        if softlock and step >= 12:
            pass  # wedged in the corner: position stops changing
        elif escape:
            x += 0.6  # marches straight out of the play area
        else:
            x = (x + 0.5) % 8.0
            y = (y + 0.25) % 6.0
            reachable = min(20, reachable + (1 if step % 10 == 0 else 0))

        emit(t=step, kind="tick", state_hash=state_hash(x, y, step),
             pos=[round(x, 2), round(y, 2)], reachable=reachable)

    if not (softlock or escape):
        emit(t=TICKS, kind="goal", message="reached the exit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
