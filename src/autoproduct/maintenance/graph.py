"""Checkpointed Maintenance graph (§09.12, plan D15).

Same rebuild as deploy/graph.py: the straight-line run_maintenance body
becomes a LangGraph StateGraph on the shared `.mas/checkpoints.db` saver
(thread ids `incident:<id>`), so a crash between triage and root-cause
resumes instead of re-paying the pipeline. Mirror step names are
preserved exactly (intake → correlate → triage → [learned_skill] →
[root_cause] → [skill_drafted] → final), the 60-point confidence floor
and P4 skip-root-cause routing are unchanged, and nothing here mutates
production — that ceiling is architectural (§08.1.8).
"""

from __future__ import annotations

import functools
import time
import uuid
from pathlib import Path
from typing import Any, TypedDict

import yaml
from langgraph.graph import END, StateGraph

from autoproduct.maintenance.correlate import Suspect, correlate
from autoproduct.maintenance.review import (
    CONFIDENCE_MIN,
    _ROOTCAUSE_SYSTEM,
    _TRIAGE_SYSTEM,
    Incident,
    MaintenanceResult,
    MaintenanceVerdict,
    RootCauseResult,
    TriageResult,
    _render_suspects,
)
from autoproduct.mirror import YamlMirror
from autoproduct.orchestrator.checkpoint import build_saver, encryption_status
from autoproduct.providers import get_provider
from autoproduct.yamlx import extract_mapping


class MaintenanceState(TypedDict, total=False):
    incident: dict
    repo_dir: str
    provider: str
    triage_model: str
    rootcause_model: str
    days: int
    started_at: float  # wall clock — survives resume, unlike monotonic
    suspects: list[dict]
    triage: dict
    learned: dict | None
    root_cause: dict | None
    result: dict


def _incident(state: MaintenanceState) -> Incident:
    return Incident.model_validate(state["incident"])


def intake_node(state: MaintenanceState, *, mirror: YamlMirror) -> dict[str, Any]:
    mirror.write("intake", {"incident": state["incident"]})
    return {}


def correlate_node(state: MaintenanceState, *, mirror: YamlMirror) -> dict[str, Any]:
    suspects = correlate(
        _incident(state).text, state["repo_dir"], days=state.get("days", 7)
    )
    mirror.write("correlate", {"suspects": [s.__dict__ for s in suspects]})
    return {"suspects": [s.__dict__ for s in suspects]}


def triage_node(state: MaintenanceState, *, mirror: YamlMirror) -> dict[str, Any]:
    provider_impl = get_provider(state["provider"])
    raw = provider_impl.complete(
        model=state["triage_model"],
        system=_TRIAGE_SYSTEM,
        user=f"<incident>\n{_incident(state).text}\n</incident>",
        max_tokens=512,
    )
    triage = TriageResult.model_validate(extract_mapping(raw, ("priority",)))
    mirror.write("triage", {"triage": triage.model_dump(mode="json")})
    return {"triage": triage.model_dump(mode="json")}


def learned_node(state: MaintenanceState, *, mirror: YamlMirror) -> dict[str, Any]:
    from autoproduct.maintenance import skills_registry

    learned = skills_registry.match(
        _incident(state).text, skills_registry.load_registry(state["repo_dir"])
    )
    if not learned:
        return {"learned": None}
    mirror.write(
        "learned_skill", {"applied": learned.name, "description": learned.description}
    )
    return {
        "learned": {
            "name": learned.name,
            "description": learned.description,
            "body": learned.body,
        }
    }


def rootcause_node(state: MaintenanceState, *, mirror: YamlMirror) -> dict[str, Any]:
    provider_impl = get_provider(state["provider"])
    suspects = [Suspect(**s) for s in state.get("suspects", [])]
    learned = state.get("learned")
    skill_block = (
        f"\n\n<learned_skill name=\"{learned['name']}\">\n{learned['body']}\n</learned_skill>"
        if learned
        else ""
    )
    raw = provider_impl.complete(
        model=state["rootcause_model"],
        system=_ROOTCAUSE_SYSTEM,
        user=(
            f"<incident>\n{_incident(state).text}\n</incident>\n\n"
            f"<suspect_commits>\n{_render_suspects(suspects)}\n</suspect_commits>"
            f"{skill_block}"
        ),
        max_tokens=1024,
    )
    root_cause = RootCauseResult.model_validate(extract_mapping(raw, ("hypothesis",)))
    mirror.write("root_cause", {"root_cause": root_cause.model_dump(mode="json")})
    return {"root_cause": root_cause.model_dump(mode="json")}


def finalize_node(state: MaintenanceState, *, mirror: YamlMirror) -> dict[str, Any]:
    from autoproduct.maintenance import skills_registry

    incident = _incident(state)
    triage = TriageResult.model_validate(state["triage"])
    root_cause = (
        RootCauseResult.model_validate(state["root_cause"])
        if state.get("root_cause")
        else None
    )
    learned = state.get("learned")

    if triage.priority == "P4":
        verdict = MaintenanceVerdict.TRIAGED_LOW_PRIORITY
    elif root_cause and root_cause.confidence >= CONFIDENCE_MIN:
        verdict = MaintenanceVerdict.ROOT_CAUSE_PROPOSED
    else:
        verdict = MaintenanceVerdict.ESCALATE_INCIDENT_UNRESOLVED

    similar = skills_registry.record_incident(
        state["repo_dir"], incident.id, incident.text
    )
    drafted = None
    if len(similar) + 1 >= skills_registry.RECURRENCE_THRESHOLD:
        drafted = skills_registry.maybe_draft_skill(
            state["repo_dir"],
            [e.get("text", "") for e in similar] + [incident.text],
            provider=state["provider"],
            model=state["triage_model"],
        )
        if drafted:
            mirror.write(
                "skill_drafted",
                {"name": drafted.name, "status": drafted.status, "path": drafted.path},
            )

    result = MaintenanceResult(
        incident_id=incident.id,
        verdict=verdict,
        triage=triage,
        root_cause=root_cause,
        suspects=state.get("suspects", []),
        summary=(
            f"{verdict.value} — {triage.priority}/{triage.category}; "
            + (
                f"hypothesis at {root_cause.confidence}% confidence"
                if root_cause
                else "no root-cause pass (P4)"
            )
            + f"; {len(state.get('suspects', []))} suspect commit(s)"
            + (f"; learned skill applied: {learned['name']}" if learned else "")
            + (f"; skill drafted: {drafted.name} (proposed)" if drafted else "")
            + f"; {time.time() - state['started_at']:.0f}s"
        ),
        artifacts_dir=str(mirror.dir),
    )
    mirror.write("final", result.model_dump(mode="json"))
    return {"result": result.model_dump(mode="json")}


def build_maintenance_graph(*, repo_dir: str = ".", incident_id: str | None = None):
    incident_id = incident_id or uuid.uuid4().hex[:12]
    mirror = YamlMirror(Path(repo_dir) / ".mas" / "incidents", incident_id)

    graph = StateGraph(MaintenanceState)
    graph.add_node("intake", functools.partial(intake_node, mirror=mirror))
    graph.add_node("correlate", functools.partial(correlate_node, mirror=mirror))
    graph.add_node("triage", functools.partial(triage_node, mirror=mirror))
    graph.add_node("learned", functools.partial(learned_node, mirror=mirror))
    graph.add_node("root_cause", functools.partial(rootcause_node, mirror=mirror))
    graph.add_node("finalize", functools.partial(finalize_node, mirror=mirror))
    graph.set_entry_point("intake")
    graph.add_edge("intake", "correlate")
    graph.add_edge("correlate", "triage")
    graph.add_edge("triage", "learned")
    graph.add_conditional_edges(
        "learned",
        lambda s: "root_cause"
        if s["triage"]["priority"] in ("P1", "P2", "P3")
        else "finalize",
    )
    graph.add_edge("root_cause", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=build_saver(repo_dir)), incident_id


def _thread(incident_id: str) -> dict:
    return {"configurable": {"thread_id": f"incident:{incident_id}"}}


def run_maintenance(
    incident: Incident,
    *,
    repo_dir: str = ".",
    provider: str = "anthropic",
    triage_model: str = "claude-haiku-4-5-20251001",
    rootcause_model: str = "claude-opus-4-8",
    days: int = 7,
) -> MaintenanceResult:
    app, _ = build_maintenance_graph(repo_dir=repo_dir, incident_id=incident.id)
    meta = {
        "incident_id": incident.id,
        "repo_dir": repo_dir,
        "provider": provider,
        "triage_model": triage_model,
        "rootcause_model": rootcause_model,
        "days": days,
        "checkpoint_encryption": encryption_status(),
    }
    meta_path = Path(repo_dir) / ".mas" / "incidents" / incident.id / "meta.yaml"
    meta_path.write_text(yaml.safe_dump(meta), encoding="utf-8")

    initial: MaintenanceState = {
        "incident": incident.model_dump(mode="json"),
        "repo_dir": repo_dir,
        "provider": provider,
        "triage_model": triage_model,
        "rootcause_model": rootcause_model,
        "days": days,
        "started_at": time.time(),
    }
    final = app.invoke(initial, config=_thread(incident.id))
    return MaintenanceResult.model_validate(final["result"])


def recover_maintenance(repo_dir: str = ".") -> list[dict]:
    """Incidents with a meta.yaml but no final mirror step continue from
    their SQLite checkpoint — same recovery contract as code review."""
    base = Path(repo_dir) / ".mas" / "incidents"
    results: list[dict] = []
    if not base.is_dir():
        return results
    for run_dir in sorted(base.iterdir()):
        meta_path = run_dir / "meta.yaml"
        if not meta_path.exists() or list(run_dir.glob("[0-9]*-final.yaml")):
            continue
        incident_id = run_dir.name
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        try:
            app, _ = build_maintenance_graph(
                repo_dir=meta["repo_dir"], incident_id=incident_id
            )
            config = _thread(incident_id)
            snapshot = app.get_state(config)
            if not snapshot.values:
                results.append(
                    {"kind": "incident", "id": incident_id, "status": "no_checkpoint"}
                )
                continue
            final = app.invoke(None, config=config)
            results.append(
                {
                    "kind": "incident",
                    "id": incident_id,
                    "status": "recovered",
                    "verdict": (final.get("result") or {}).get("verdict"),
                }
            )
        except Exception as exc:  # noqa: BLE001 — one broken run never blocks the rest
            results.append(
                {"kind": "incident", "id": incident_id, "status": "error",
                 "detail": str(exc)[:200]}
            )
    return results
