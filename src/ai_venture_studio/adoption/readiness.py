"""Readiness report generator (§19 G1 Day 4).

Profile in, markdown out: active stages, missing rungs, and what each
missing rung would unlock — the modernization-roadmap framing of §18.47.1.
The report is a deliverable for the adopting team's platform organization,
so it must read correctly to a non-author.
"""

from __future__ import annotations

from ai_venture_studio.adoption.substrate import (
    RUNG_REQUIREMENTS,
    STAGE_FLOORS,
    Rung,
    StageStatus,
    SubstrateProfile,
    rung_banner,
    stage_activation,
)

_STAGE_ORDER = [
    "discovery", "planning", "specification", "coding",
    "code_review", "test", "deploy_review", "maintenance",
]

_STAGE_VALUE = {
    "discovery": "briefs + hypothesis ledger through Gate U1",
    "planning": "task DAG + lanes + budget through Gate U2",
    "specification": "design.md + EARS acceptance criteria through Gate U3",
    "coding": "single-writer implementation lanes with the build gate",
    "code_review": "heterogeneous voters + verified findings on every PR",
    "test": "mutation testing and generated UI/flow tests",
    "deploy_review": "CI/CD, IaC, and canary-policy review before exposure",
    "maintenance": "incident triage/root-cause/fix-PR over production signals",
}


def readiness_report(profile: SubstrateProfile, project_name: str = "") -> str:
    rung = profile.rung()
    title = f"# Substrate readiness — {project_name}" if project_name else "# Substrate readiness"
    lines = [
        title,
        "",
        f"**{rung_banner(profile)}**",
        "",
        "| Stage | Status | Floor | What it gives you |",
        "|---|---|---|---|",
    ]
    for stage in _STAGE_ORDER:
        act = stage_activation(profile, stage)
        status = {
            StageStatus.ACTIVE: "active",
            StageStatus.DEGRADED: f"degraded ({act.note.split(' — ')[0]})",
            StageStatus.STAGE_INACTIVE: "inactive",
        }[act.status]
        lines.append(
            f"| {stage} | {status} | {act.rung_required} | {_STAGE_VALUE[stage]} |"
        )

    next_rungs = [r for r in Rung if r > rung]
    if next_rungs:
        lines += ["", "## Roadmap — what each missing rung unlocks", ""]
        for step in next_rungs:
            unlocked = sorted(
                s for s, floor in STAGE_FLOORS.items() if floor == step
            )
            stages = ", ".join(unlocked) if unlocked else "(hardening only)"
            lines.append(
                f"- **{step.label}** — add {RUNG_REQUIREMENTS[step]} → unlocks: {stages}"
            )
    else:
        lines += ["", "All rungs met — every stage is active at full depth."]
    lines.append("")
    return "\n".join(lines)
