"""`.mas/strategy.yaml` (§20.54.3) — the stated strategy constraints the
Fit voter judges distance against.

Human-owned, optional: an absent file means no declared constraints (the
Fit voter then judges distance from product and stack alone). A present
file that does not parse fails loudly — silently ignoring a strategy file
is how a voter charter references a ghost.
"""

from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field

STRATEGY_FILE = "strategy.yaml"


class Strategy(BaseModel):
    product: str = ""  # one line: what the product is today
    stack: str = ""  # one line: the stack candidates should ride
    segments: list[str] = Field(default_factory=list)  # who we serve
    constraints: list[str] = Field(default_factory=list)  # hard strategy rules


class StrategyError(RuntimeError):
    """Malformed strategy file. Fails loudly, never silently ignored."""


def load_strategy(mas_dir: str | pathlib.Path) -> Strategy:
    path = pathlib.Path(mas_dir) / STRATEGY_FILE
    if not path.exists():
        return Strategy()
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise StrategyError(f"{STRATEGY_FILE}: {exc}") from exc
    if not isinstance(raw, dict):
        raise StrategyError(f"{STRATEGY_FILE} must be a mapping")
    try:
        return Strategy(**raw)
    except ValueError as exc:
        raise StrategyError(f"{STRATEGY_FILE}: {exc}") from exc
