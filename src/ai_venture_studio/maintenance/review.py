"""Maintenance MAS (§09.12) — triage + root-cause, insight/assistive tier.

Skeleton scope (v0.8.0 start): incident intake from a file (webhook ingest
lands with server mode), deterministic PR correlation, a Triage pass and a
RootCause investigation with repo tools. Fix-PR generation is the assistive
next step and re-enters Code Review like any PR; nothing here mutates
production — that ceiling is architectural (§08.1.8).

Confidence discipline mirrors the design: a root-cause hypothesis below the
60-point bar escalates instead of pretending certainty.

This module holds the stage's primitives (incident model, verdicts,
prompts); the checkpointed orchestration lives in `maintenance/graph.py`
since v0.32 (plan D15) — `run_maintenance` is re-exported from there
unchanged.
"""

from __future__ import annotations

import enum
import json
import uuid
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ai_venture_studio.maintenance.correlate import Suspect

CONFIDENCE_MIN = 60

TRIAGE_MARKER = "triage stage of a production-maintenance system"
ROOTCAUSE_MARKER = "root-cause investigator in a production-maintenance system"


class Incident(BaseModel):
    id: str
    title: str
    body: str = ""
    source: str = "manual"
    external_id: str = Field(
        default="",
        description="the id in the source system (e.g. a Sentry issue id) — "
        "what the signal readers in maintenance/signals.py resolve",
    )

    @classmethod
    def load(cls, path: str | Path) -> "Incident":
        raw = Path(path).read_text(encoding="utf-8")
        if str(path).endswith((".json", ".yaml", ".yml")):
            data = json.loads(raw) if str(path).endswith(".json") else yaml.safe_load(raw)
            data.setdefault("id", uuid.uuid4().hex[:12])
            return cls.model_validate(data)
        lines = raw.splitlines()
        if not lines or not raw.strip():
            raise ValueError(f"incident file {path} is empty")
        return cls(id=uuid.uuid4().hex[:12], title=lines[0][:120], body=raw)

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}"


class MaintenanceVerdict(str, enum.Enum):
    TRIAGED_LOW_PRIORITY = "TRIAGED_LOW_PRIORITY"
    ROOT_CAUSE_PROPOSED = "ROOT_CAUSE_PROPOSED"  # assistive: fix-PR is the next step
    ESCALATE_INCIDENT_UNRESOLVED = "ESCALATE_INCIDENT_UNRESOLVED"


class TriageResult(BaseModel):
    priority: str = Field(pattern=r"^P[1-4]$")
    category: str
    rationale: str


class RootCauseResult(BaseModel):
    hypothesis: str
    confidence: int = Field(ge=0, le=100)
    implicated_commit: str | None = None
    implicated_files: list[str] = Field(default_factory=list)
    next_action: str = ""


class MaintenanceResult(BaseModel):
    incident_id: str
    verdict: MaintenanceVerdict
    triage: TriageResult | None = None
    root_cause: RootCauseResult | None = None
    suspects: list[dict] = Field(default_factory=list)
    summary: str = ""
    artifacts_dir: str = ""


_TRIAGE_SYSTEM = f"""You are the {TRIAGE_MARKER}. Classify the incident.

P1 = user-facing outage or data loss, act now. P2 = degraded core flow.
P3 = contained bug or noisy error. P4 = cosmetic / cleanup.

Respond with ONLY YAML:
priority: P1|P2|P3|P4
category: crash | data | performance | security | integration | noise
rationale: one sentence
"""

_ROOTCAUSE_SYSTEM = f"""You are a {ROOTCAUSE_MARKER}. Form ONE hypothesis
about the cause of the incident, grounded in the suspect commits provided —
they are ranked by deterministic correlation with the incident text. Do not
invent code or commits; if the evidence is thin, say so with low confidence.

Respond with ONLY YAML:
hypothesis: ...
confidence: 0-100        # below {CONFIDENCE_MIN} means "needs human/more investigation"
implicated_commit: sha or null
implicated_files: []
next_action: one sentence (e.g. the fix-PR to propose, or what to check)
"""


def _render_suspects(suspects: list[Suspect]) -> str:
    if not suspects:
        return "(no recent commits correlate with the incident text)"
    return "\n".join(
        f"- {s.sha} (score {s.score}) {s.subject} — files: {', '.join(s.files[:6])}"
        for s in suspects
    )
