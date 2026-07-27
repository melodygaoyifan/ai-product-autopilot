"""L1/L2 tool implementations served over MCP (doc 11 §17.2, second half).

The §17.2 table names eight servers. v0.37 shipped the two L0 ones; v0.40
partitioned the L1/L2 tools that already existed, and v0.43 added the first
external-service integration. What is still unbuilt (`terraform_validate`,
`datadog_query_metrics`, and the rest) stays named as open rather than
stubbed — a shim that isolates nothing would be exactly the dishonesty the
map's "open" column exists to prevent.

This module holds the L1/L2 tool implementations:

| server | risk | tools | what it wraps |
|---|---|---|---|
| `deploy` | L1 | `migration_scan`, `workflow_scan`, `canary_scan` | the deterministic deploy probes |
| `maintenance` | L1 | `recent_commits`, `correlate`, and the six §17.2 signal readers (sentry/datadog/pagerduty/prometheus/loki/jaeger) | git history, incident↔commit correlation, external production signals |
| `test_exec` | L2 | `run_tests` | the test gate, which EXECUTES repo code |

What this buys beyond the in-process call:

1. **Risk-tier RBAC at the transport.** Each server declares a risk level;
   `MCPHost` refuses to mount one above the caller's ceiling. A voter
   declaring `risk_ceiling: 0` cannot reach an L1 server even if some
   future skill lists one of its tools — the ceiling is enforced where the
   connection is made, not where the prompt is written.
2. **Audit coverage for the tools that mutate the most.** Deploy probes and
   test execution were previously unaudited; now every call lands in
   `.mas/mcp-audit.jsonl` like every L0 call.
3. **Subprocess isolation where it matters most.** §17.2's reasoning for
   `test_exec` being L2 is that tests execute code, so a malicious test
   could otherwise affect the harness process. That is now a child process.

The external-service tools (v0.43-v0.44) proved that claim: all six §17.2
signal readers are registrations in this table plus one shared reader module,
with no change to the transport, the host, or the RBAC. What remains unbuilt
is the deploy-side CLI wrappers (terraform/helm/kubectl), which are a
different shape — binaries rather than HTTP.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Callable

# tool name → (risk level, callable(root, **args) -> str)
_IMPLS: dict[str, tuple[int, Callable[..., str]]] = {}


def _register(name: str, risk: int):
    def decorate(fn: Callable[..., str]) -> Callable[..., str]:
        _IMPLS[name] = (risk, fn)
        return fn

    return decorate


def stage_tool_names() -> list[str]:
    return sorted(_IMPLS)


def risk_of(tool: str) -> int | None:
    entry = _IMPLS.get(tool)
    return entry[0] if entry else None


def call_stage_tool(tool: str, root: str | pathlib.Path, args: dict) -> str:
    """Dispatch one L1/L2 tool. Errors come back as data, like the L0 box."""
    entry = _IMPLS.get(tool)
    if entry is None:
        return f"error: unknown stage tool {tool!r}"
    _risk, fn = entry
    try:
        return fn(pathlib.Path(root).resolve(), **(args or {}))
    except TypeError as exc:
        return f"error: bad arguments for {tool}: {exc}"
    except Exception as exc:  # noqa: BLE001 — tool errors travel as data
        return f"error: {type(exc).__name__}: {exc}"


def _report(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


# --- deploy server (L1): the deterministic deploy probes ----------------------


def _scan(kind: str, root: pathlib.Path, diff_text: str) -> str:
    from autoproduct.deploy.probes import canary_scan, migration_scan, workflow_scan
    from autoproduct.diff import parse_unified_diff

    scanner = {"migration": migration_scan, "workflow": workflow_scan,
               "canary": canary_scan}[kind]
    report = scanner(parse_unified_diff(diff_text), str(root))
    return _report(report.model_dump(mode="json"))


@_register("migration_scan", 1)
def migration_scan_tool(root: pathlib.Path, diff_text: str) -> str:
    return _scan("migration", root, diff_text)


@_register("workflow_scan", 1)
def workflow_scan_tool(root: pathlib.Path, diff_text: str) -> str:
    return _scan("workflow", root, diff_text)


@_register("canary_scan", 1)
def canary_scan_tool(root: pathlib.Path, diff_text: str) -> str:
    return _scan("canary", root, diff_text)


# --- maintenance server (L1): production-signal reading ----------------------


@_register("recent_commits", 1)
def recent_commits_tool(root: pathlib.Path, days: int = 7, limit: int = 30) -> str:
    from autoproduct.maintenance.correlate import recent_commits

    return _report(recent_commits(str(root), days=int(days), limit=int(limit)))


def _signal(report) -> str:
    """A reader's result as tool output. A skip or error is reported as
    itself, never rendered as an empty read; an ok payload travels wrapped
    so consuming it taints the run out of L1+ (ADR-U03)."""
    if report.status != "ok":
        return _report({"status": report.status, "detail": report.detail})
    return report.wrapped


@_register("sentry_get_issue", 1)
def sentry_get_issue_tool(root: pathlib.Path, issue_id: str) -> str:
    from autoproduct.maintenance.signals import sentry_get_issue

    return _signal(sentry_get_issue(issue_id))


@_register("datadog_query_metrics", 1)
def datadog_query_metrics_tool(
    root: pathlib.Path, query: str, from_ts: int, to_ts: int
) -> str:
    """The window is required, not defaulted: a metric read whose window
    nobody stated is not evidence."""
    from autoproduct.maintenance.signals import datadog_query_metrics

    return _signal(datadog_query_metrics(query, from_ts=from_ts, to_ts=to_ts))


@_register("pagerduty_get_incident", 1)
def pagerduty_get_incident_tool(root: pathlib.Path, incident_id: str) -> str:
    from autoproduct.maintenance.signals import pagerduty_get_incident

    return _signal(pagerduty_get_incident(incident_id))


@_register("prometheus_query", 1)
def prometheus_query_tool(root: pathlib.Path, query: str, at: str = "") -> str:
    from autoproduct.maintenance.signals import prometheus_query

    return _signal(prometheus_query(query, at=at or None))


@_register("loki_query", 1)
def loki_query_tool(
    root: pathlib.Path, query: str, start: str = "", end: str = "", limit: int = 100
) -> str:
    from autoproduct.maintenance.signals import loki_query

    return _signal(
        loki_query(query, start=start or None, end=end or None, limit=int(limit))
    )


@_register("jaeger_query_trace", 1)
def jaeger_query_trace_tool(root: pathlib.Path, trace_id: str) -> str:
    from autoproduct.maintenance.signals import jaeger_query_trace

    return _signal(jaeger_query_trace(trace_id))


@_register("correlate", 1)
def correlate_tool(root: pathlib.Path, incident_text: str, days: int = 7) -> str:
    from autoproduct.maintenance.correlate import correlate

    suspects = correlate(incident_text, str(root), days=int(days))
    return _report([s.__dict__ for s in suspects])


# --- test_exec server (L2): the one that executes repo code ------------------


@_register("run_tests", 2)
def run_tests_tool(root: pathlib.Path, diff_text: str = "", mode: str = "standard") -> str:
    """Run the repo's test gate. L2 because this executes the repository's
    own code — §17.2's reason for isolating it hardest."""
    from autoproduct.testing import run_test_gate

    report = run_test_gate(str(root), diff_text, mode=mode)
    return _report(report.model_dump(mode="json"))
