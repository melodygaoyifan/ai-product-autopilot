"""The inner→outer handoff (§21.57.4) — release_to_p3.yaml.

`claims_available` is the substantiation register: what marketing is
permitted to say, and no more. P3 may not assert a product capability that
is not in it — this single field converts "don't make unsubstantiated
claims" from an instruction into a lookup, which is the difference between
a guideline and a gate.

`instrumentation_verified` is a Gate PL3 precondition: a campaign that
ships without instrumentation cannot be evaluated, and an outer loop that
cannot evaluate is not a loop.
"""

from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field


class RegisteredClaim(BaseModel):
    id: str
    text: str
    source_type: str
    evidence: list[dict] = Field(default_factory=list)
    n: int | None = None
    typical_results: bool = False  # basis for outcome claims (§21.58.2)


class ReleaseContract(BaseModel):
    prd_ref: str
    changelog_refs: list[str] = Field(default_factory=list)
    outcomes_ref: str = ""
    instrumentation_verified: bool = False
    claims_available: list[RegisteredClaim] = Field(default_factory=list)
    rollout: dict = Field(default_factory=dict)

    def claim(self, claim_id: str) -> RegisteredClaim | None:
        for c in self.claims_available:
            if c.id == claim_id:
                return c
        return None


class ReleaseContractError(RuntimeError):
    """Raised on a malformed release_to_p3.yaml. A handoff that does not
    validate fails here rather than being interpreted."""


def load_release_contract(path: str | pathlib.Path) -> ReleaseContract:
    try:
        raw = yaml.safe_load(pathlib.Path(path).read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise ReleaseContractError(f"cannot read release contract: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("release"), dict):
        raise ReleaseContractError("release_to_p3.yaml must contain a 'release' mapping")
    try:
        return ReleaseContract(**raw["release"])
    except ValueError as exc:
        raise ReleaseContractError(f"malformed release contract: {exc}") from exc
