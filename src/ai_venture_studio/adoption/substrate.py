"""Substrate adoption ladder (§18.47.1, ADR-U15).

`.mas/substrate-profile.yaml` declares what the adopting team actually has;
the rung it computes activates only the stages whose infrastructure floor is
met. A stage below its floor is INACTIVE with a structured notice — never a
silent skip. Deploy Review is the one named exception: from S1 it may run in
config-lint-only DEGRADED mode, and its banner says so.

No profile file means no gating: the ladder is opt-in, and existing
workspaces (which all run at effective S4) behave exactly as before.
"""

from __future__ import annotations

import enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

PROFILE_FILENAME = ".mas/substrate-profile.yaml"

_KNOWN_OBSERVABILITY = {"sentry", "datadog", "pagerduty", "none"}


class Rung(int, enum.Enum):
    """S0 artifacts+humans · S1 +git/PR · S2 +CI · S3 +observability ·
    S4 +progressive delivery."""

    S0 = 0
    S1 = 1
    S2 = 2
    S3 = 3
    S4 = 4

    @property
    def label(self) -> str:
        return f"S{self.value}"


# What climbing to each rung unlocks — the readiness report renders this
# as the modernization roadmap (§18.47.1 table).
RUNG_REQUIREMENTS: dict[Rung, str] = {
    Rung.S1: "git + PR flow",
    Rung.S2: "CI (machine-runnable build+test on every change)",
    Rung.S3: "observability (Sentry/Datadog/PagerDuty-class)",
    Rung.S4: "progressive delivery (canary/staged rollout)",
}

STAGE_FLOORS: dict[str, Rung] = {
    "discovery": Rung.S0,
    "planning": Rung.S0,
    "specification": Rung.S0,
    "coding": Rung.S1,
    "code_review": Rung.S1,
    "test": Rung.S2,
    "maintenance": Rung.S3,
    "deploy_review": Rung.S4,
}

# Deploy Review's named degraded mode: config lint needs a repo to diff,
# nothing more (§18.47.1).
_DEPLOY_REVIEW_DEGRADED_FLOOR = Rung.S1


class StageStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    STAGE_INACTIVE = "STAGE_INACTIVE"


class StageActivation(BaseModel):
    stage: str
    status: StageStatus
    rung_required: str
    rung_present: str
    note: str = ""


class StageInactiveError(Exception):
    """Raised by check_stage when routing to a below-floor stage."""

    def __init__(self, activation: StageActivation):
        self.activation = activation
        super().__init__(
            f"STAGE_INACTIVE(stage={activation.stage}, "
            f"rung_required={activation.rung_required}, "
            f"rung_present={activation.rung_present}) — {activation.note}"
        )


class SubstrateProfile(BaseModel):
    """Structural mirror of `.mas/substrate-profile.yaml` (§19 G1 Day 2)."""

    vcs: str = Field(pattern="^(git|none)$")
    pr_flow: bool = False
    ci: bool = False
    observability: list[str] = Field(default_factory=lambda: ["none"])
    progressive_delivery: bool = False
    languages: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _structural(self) -> SubstrateProfile:
        if self.pr_flow and self.vcs != "git":
            raise ValueError("pr_flow: true requires vcs: git")
        unknown = set(self.observability) - _KNOWN_OBSERVABILITY
        if unknown:
            raise ValueError(
                f"unknown observability values {sorted(unknown)}; "
                f"known: {sorted(_KNOWN_OBSERVABILITY)}"
            )
        if self.progressive_delivery and not self.ci:
            raise ValueError("progressive_delivery: true requires ci: true")
        return self

    @property
    def has_observability(self) -> bool:
        return any(o != "none" for o in self.observability)

    def rung(self) -> Rung:
        """Highest rung whose floor is fully met — rungs are cumulative."""
        if not (self.vcs == "git" and self.pr_flow):
            return Rung.S0
        if not self.ci:
            return Rung.S1
        if not self.has_observability:
            return Rung.S2
        if not self.progressive_delivery:
            return Rung.S3
        return Rung.S4

    def missing_for(self, rung: Rung) -> list[str]:
        gaps = []
        for step in Rung:
            if step == Rung.S0 or step > rung:
                continue
            if step > self.rung():
                gaps.append(RUNG_REQUIREMENTS[step])
        return gaps


def load_substrate_profile(repo_dir: str | Path) -> SubstrateProfile | None:
    """None when the file is absent (ladder not adopted — no gating).
    Malformed content is a hard error with the field named, not a default."""
    path = Path(repo_dir) / PROFILE_FILENAME
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "substrate" not in data:
        raise ValueError(
            f"{path}: expected a top-level 'substrate:' mapping "
            "(see §18.47.1 for the schema)"
        )
    try:
        return SubstrateProfile(**data["substrate"])
    except Exception as exc:  # pydantic ValidationError carries the field
        raise ValueError(f"{path}: invalid substrate profile — {exc}") from exc


def stage_activation(profile: SubstrateProfile, stage: str) -> StageActivation:
    if stage not in STAGE_FLOORS:
        raise ValueError(
            f"unknown stage {stage!r}; known: {sorted(STAGE_FLOORS)}"
        )
    floor = STAGE_FLOORS[stage]
    present = profile.rung()
    if present >= floor:
        return StageActivation(
            stage=stage, status=StageStatus.ACTIVE,
            rung_required=floor.label, rung_present=present.label,
        )
    if stage == "deploy_review" and present >= _DEPLOY_REVIEW_DEGRADED_FLOOR:
        return StageActivation(
            stage=stage, status=StageStatus.DEGRADED,
            rung_required=floor.label, rung_present=present.label,
            note="config-lint-only degraded mode — canary machinery needs "
            f"{RUNG_REQUIREMENTS[Rung.S4]}",
        )
    missing = " · ".join(profile.missing_for(floor))
    return StageActivation(
        stage=stage, status=StageStatus.STAGE_INACTIVE,
        rung_required=floor.label, rung_present=present.label,
        note=f"missing: {missing}",
    )


def check_stage(repo_dir: str | Path, stage: str) -> StageActivation | None:
    """Dispatcher guard (§19 G1 Day 3). No-op (None) when no profile is
    declared; raises StageInactiveError below the floor."""
    profile = load_substrate_profile(repo_dir)
    if profile is None:
        return None
    activation = stage_activation(profile, stage)
    if activation.status is StageStatus.STAGE_INACTIVE:
        raise StageInactiveError(activation)
    return activation


def rung_banner(profile: SubstrateProfile) -> str:
    """One-liner carried on every artifact/verdict banner (F-18.5: the rung
    is visible so an S0 wedge is never mistaken for full adoption)."""
    rung = profile.rung()
    inactive = [
        s for s in STAGE_FLOORS
        if stage_activation(profile, s).status is StageStatus.STAGE_INACTIVE
    ]
    scope = "all stages active" if not inactive else f"inactive: {', '.join(sorted(inactive))}"
    return f"substrate rung {rung.label} — {scope}"
