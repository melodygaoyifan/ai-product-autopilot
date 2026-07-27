"""External production-signal readers (doc 11 §17.2 `maintenance_server`).

All six tools the §17.2 table names, over one shared read-only core:

| tool | service | gate |
|---|---|---|
| `sentry_get_issue` | Sentry | `AUTOPRODUCT_SENTRY_TOKEN` |
| `datadog_query_metrics` | Datadog | `AUTOPRODUCT_DATADOG_API_KEY` + `_APP_KEY` |
| `pagerduty_get_incident` | PagerDuty | `AUTOPRODUCT_PAGERDUTY_TOKEN` |
| `prometheus_query` | Prometheus | `AUTOPRODUCT_PROMETHEUS_URL` |
| `loki_query` | Loki | `AUTOPRODUCT_LOKI_URL` |
| `jaeger_query_trace` | Jaeger | `AUTOPRODUCT_JAEGER_URL` |

**Two gating families, deliberately distinguished.** A hosted service is
gated on its *credential* (no key, no call). A self-hosted one is gated on
its *base URL*, because there is no sensible default for a Prometheus that
lives at a different address in every deployment — and defaulting to
localhost would turn "not configured" into a confusing connection error.
Either way an unconfigured reader returns `status="skipped"` naming the
exact variable to set: "never asked" must never read like "nothing found"
(the rule `tools/external.py` set for scanners).

**Read-only, by construction.** Every reader issues a GET with no body.
None of these tools can acknowledge a PagerDuty incident, resolve a Sentry
issue, or write a Datadog event — L1 means read, and the maintenance stage
recommends rather than acts.

**Every payload is untrusted.** Issue titles, log lines, span operation
names and monitor messages all echo text that users and third parties
supplied. Each reader wraps its payload with `wrap_research`, so it is data
a hypothesis may cite and never an instruction, and consuming it taints the
run out of L1+ tools (ADR-U03).

**Honest scope.** These are written against each vendor's documented REST
API and exercised hermetically against a stub transport. None has been run
against a live account from this repository — no credentials exist here to
do that with. The first live call per service is a real verification step
that remains outstanding, and the implementation map says so per tool
rather than implying coverage that does not exist.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

TIMEOUT_S = 15
MIN_SCRUBBABLE = 8

# --- hosted services: gated on a credential ----------------------------------
SENTRY_TOKEN_ENV = "AUTOPRODUCT_SENTRY_TOKEN"
SENTRY_BASE_ENV = "AUTOPRODUCT_SENTRY_BASE_URL"
DEFAULT_BASE_URL = "https://sentry.io/api/0"

DATADOG_API_KEY_ENV = "AUTOPRODUCT_DATADOG_API_KEY"
DATADOG_APP_KEY_ENV = "AUTOPRODUCT_DATADOG_APP_KEY"
DATADOG_BASE_ENV = "AUTOPRODUCT_DATADOG_BASE_URL"
DATADOG_DEFAULT_BASE = "https://api.datadoghq.com/api/v1"

PAGERDUTY_TOKEN_ENV = "AUTOPRODUCT_PAGERDUTY_TOKEN"
PAGERDUTY_BASE_ENV = "AUTOPRODUCT_PAGERDUTY_BASE_URL"
PAGERDUTY_DEFAULT_BASE = "https://api.pagerduty.com"

# --- self-hosted: gated on a base URL ----------------------------------------
PROMETHEUS_URL_ENV = "AUTOPRODUCT_PROMETHEUS_URL"
PROMETHEUS_TOKEN_ENV = "AUTOPRODUCT_PROMETHEUS_TOKEN"  # optional bearer
LOKI_URL_ENV = "AUTOPRODUCT_LOKI_URL"
LOKI_TOKEN_ENV = "AUTOPRODUCT_LOKI_TOKEN"  # optional bearer
JAEGER_URL_ENV = "AUTOPRODUCT_JAEGER_URL"
JAEGER_TOKEN_ENV = "AUTOPRODUCT_JAEGER_TOKEN"  # optional bearer


class SignalReport(BaseModel):
    tool: str
    status: str  # ok | skipped | error
    detail: str = ""
    # The wrapped, untrusted payload. Empty unless status == "ok".
    wrapped: str = ""
    data: dict = Field(default_factory=dict)


class SignalGateError(RuntimeError):
    """A configured-but-unresolvable credential. Never a silent downgrade to
    an unauthenticated call."""


@dataclass
class _Call:
    """One prepared read: where to GET, with what headers, hiding which
    secrets from the eventual payload."""

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    secrets: list[str] = field(default_factory=list)


def _resolve(env_name: str) -> str | None:
    """Read an env var, honoring `secret://OTHER_VAR` indirection.

    A missing plain value means "not configured" (the caller skips). A
    `secret://` reference that cannot be resolved is an ERROR, because the
    operator clearly intended a credential to exist.
    """
    raw = (os.environ.get(env_name) or "").strip()
    if not raw:
        return None
    if raw.startswith("secret://"):
        from autoproduct.secrets import SecretError, SecretsLoader

        try:
            return SecretsLoader().resolve(raw).reveal()
        except SecretError as exc:
            raise SignalGateError(f"{env_name} could not be resolved: {exc}") from exc
    return raw


def _base(env_name: str, default: str, override: str | None = None) -> str:
    return (override or os.environ.get(env_name) or default).rstrip("/")


def _http_get(call: _Call) -> dict:
    request = urllib.request.Request(  # noqa: S310 — https/http base from config
        call.url,
        headers={"Accept": "application/json",
                 "User-Agent": "autoproduct-maintenance/1", **call.headers},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310
        return json.loads(response.read() or b"{}")


def _scrub(text: str, secrets: list[str]) -> str:
    """No credential survives into a mirror, prompt, or audit line.

    Length-floored: substring-replacing a two-character "token" would shred
    every payload containing those letters, which is a worse failure than
    not scrubbing a string too short to be a credential.
    """
    for secret in secrets:
        if secret and len(secret) >= MIN_SCRUBBABLE:
            text = text.replace(secret, "<secret:redacted>")
    return text


def _skip(tool: str, missing: str, why: str) -> SignalReport:
    return SignalReport(
        tool=tool, status="skipped",
        detail=f"{missing} not set — {why}. A skipped reader is reported, "
               "never treated as 'nothing found'.",
    )


def _read(tool: str, call: _Call, summarize, locator: str) -> SignalReport:
    """The shared body: GET, summarize, wrap, scrub. Errors become data."""
    from autoproduct.harness.taint_guard import wrap_research

    try:
        payload = _http_get(call)
    except urllib.error.HTTPError as exc:
        return SignalReport(tool=tool, status="error",
                            detail=f"{tool}: service returned {exc.code}"[:200])
    except (OSError, json.JSONDecodeError) as exc:
        return SignalReport(tool=tool, status="error",
                            detail=f"{type(exc).__name__}: {exc}"[:200])
    summary, detail = summarize(payload)
    wrapped = _scrub(
        wrap_research(json.dumps(summary, ensure_ascii=False, indent=2), locator),
        call.secrets,
    )
    return SignalReport(tool=tool, status="ok", detail=detail,
                        wrapped=wrapped, data=summary)


def _guard(tool: str, fn):
    """Turn a gate error into a reported error rather than a raise."""
    try:
        return fn()
    except SignalGateError as exc:
        return SignalReport(tool=tool, status="error", detail=str(exc)[:200])


# --- Sentry -------------------------------------------------------------------


def sentry_get_issue(issue_id: str, *, base_url: str | None = None) -> SignalReport:
    """Read one Sentry issue: culprit (where), counts (how bad), seen-window
    (when) — the fields a root-cause pass can actually use."""
    tool = "sentry_get_issue"

    def run() -> SignalReport:
        if not str(issue_id).strip():
            return SignalReport(tool=tool, status="error",
                                detail="issue_id is required")
        token = _resolve(SENTRY_TOKEN_ENV)
        if not token:
            return _skip(tool, SENTRY_TOKEN_ENV,
                         "export a Sentry auth token (or a secret://ENV "
                         "reference) to enrich incidents with their issue")
        url = (f"{_base(SENTRY_BASE_ENV, DEFAULT_BASE_URL, base_url)}"
               f"/issues/{urllib.parse.quote(str(issue_id), safe='')}/")

        def summarize(payload: dict):
            summary = {
                "id": str(payload.get("id", issue_id)),
                "title": str(payload.get("title", ""))[:300],
                "culprit": str(payload.get("culprit", ""))[:300],
                "level": str(payload.get("level", "")),
                "count": payload.get("count"),
                "user_count": payload.get("userCount"),
                "first_seen": payload.get("firstSeen"),
                "last_seen": payload.get("lastSeen"),
                "permalink": str(payload.get("permalink", ""))[:300],
            }
            return summary, (f"issue {summary['id']}: {summary['count']} event(s), "
                             f"{summary['user_count']} user(s) affected")

        return _read(tool, _Call(url, {"Authorization": f"Bearer {token}"}, [token]),
                     summarize, f"sentry://issues/{issue_id}")

    return _guard(tool, run)


# --- Datadog ------------------------------------------------------------------


def datadog_query_metrics(
    query: str, *, from_ts: int, to_ts: int, base_url: str | None = None
) -> SignalReport:
    """Query the timeseries API over an explicit window.

    The window is required rather than defaulted: "the last hour" means
    something different at read time than at incident time, and a metric
    read whose window nobody stated is not evidence.
    """
    tool = "datadog_query_metrics"

    def run() -> SignalReport:
        if not str(query).strip():
            return SignalReport(tool=tool, status="error", detail="query is required")
        api_key = _resolve(DATADOG_API_KEY_ENV)
        app_key = _resolve(DATADOG_APP_KEY_ENV)
        if not api_key or not app_key:
            missing = DATADOG_API_KEY_ENV if not api_key else DATADOG_APP_KEY_ENV
            return _skip(tool, missing,
                         "Datadog's timeseries API needs both an API key and "
                         "an application key")
        params = urllib.parse.urlencode(
            {"query": query, "from": int(from_ts), "to": int(to_ts)}
        )
        url = f"{_base(DATADOG_BASE_ENV, DATADOG_DEFAULT_BASE, base_url)}/query?{params}"

        def summarize(payload: dict):
            series = payload.get("series") or []
            points = [
                {"metric": str(s.get("metric", ""))[:200],
                 "scope": str(s.get("scope", ""))[:200],
                 "length": len(s.get("pointlist") or []),
                 "last": (s.get("pointlist") or [[None, None]])[-1]}
                for s in series[:10]
            ]
            summary = {
                "query": str(query)[:300],
                "from_ts": int(from_ts), "to_ts": int(to_ts),
                "status": str(payload.get("status", "")),
                "series_count": len(series),
                "series": points,
            }
            return summary, (f"{len(series)} series over "
                             f"{int(to_ts) - int(from_ts)}s window")

        return _read(
            tool,
            _Call(url, {"DD-API-KEY": api_key, "DD-APPLICATION-KEY": app_key},
                  [api_key, app_key]),
            summarize, f"datadog://query/{urllib.parse.quote(query, safe='')}",
        )

    return _guard(tool, run)


# --- PagerDuty ----------------------------------------------------------------


def pagerduty_get_incident(
    incident_id: str, *, base_url: str | None = None
) -> SignalReport:
    """Read one PagerDuty incident. Read-only: this cannot acknowledge,
    resolve, reassign, or add a note — the on-call human owns those."""
    tool = "pagerduty_get_incident"

    def run() -> SignalReport:
        if not str(incident_id).strip():
            return SignalReport(tool=tool, status="error",
                                detail="incident_id is required")
        token = _resolve(PAGERDUTY_TOKEN_ENV)
        if not token:
            return _skip(tool, PAGERDUTY_TOKEN_ENV,
                         "export a PagerDuty REST API token to resolve "
                         "incident ids to their detail")
        url = (f"{_base(PAGERDUTY_BASE_ENV, PAGERDUTY_DEFAULT_BASE, base_url)}"
               f"/incidents/{urllib.parse.quote(str(incident_id), safe='')}")

        def summarize(payload: dict):
            incident = payload.get("incident") or payload
            service = incident.get("service") or {}
            summary = {
                "id": str(incident.get("id", incident_id)),
                "title": str(incident.get("title", ""))[:300],
                "status": str(incident.get("status", "")),
                "urgency": str(incident.get("urgency", "")),
                "created_at": incident.get("created_at"),
                "service": str(service.get("summary", ""))[:200],
                "escalation_count": len(incident.get("pending_actions") or []),
                "html_url": str(incident.get("html_url", ""))[:300],
            }
            return summary, (f"incident {summary['id']}: {summary['status']}, "
                             f"urgency {summary['urgency']}")

        return _read(
            tool,
            _Call(url, {"Authorization": f"Token token={token}",
                        "Accept": "application/vnd.pagerduty+json;version=2"},
                  [token]),
            summarize, f"pagerduty://incidents/{incident_id}",
        )

    return _guard(tool, run)


# --- Prometheus / Loki / Jaeger: self-hosted, gated on a base URL ------------


def _optional_bearer(env_name: str) -> tuple[dict[str, str], list[str]]:
    token = _resolve(env_name)
    if not token:
        return {}, []
    return {"Authorization": f"Bearer {token}"}, [token]


def prometheus_query(query: str, *, at: str | None = None) -> SignalReport:
    """Instant query against a self-hosted Prometheus."""
    tool = "prometheus_query"

    def run() -> SignalReport:
        if not str(query).strip():
            return SignalReport(tool=tool, status="error", detail="query is required")
        base = _resolve(PROMETHEUS_URL_ENV)
        if not base:
            return _skip(tool, PROMETHEUS_URL_ENV,
                         "point this at your Prometheus (there is no sensible "
                         "default address, and guessing localhost would turn "
                         "'not configured' into a connection error)")
        params = {"query": query}
        if at:
            params["time"] = at
        url = f"{base.rstrip('/')}/api/v1/query?{urllib.parse.urlencode(params)}"
        headers, secrets = _optional_bearer(PROMETHEUS_TOKEN_ENV)

        def summarize(payload: dict):
            result = ((payload.get("data") or {}).get("result")) or []
            summary = {
                "query": str(query)[:300],
                "status": str(payload.get("status", "")),
                "result_type": str((payload.get("data") or {}).get("resultType", "")),
                "series_count": len(result),
                "samples": [
                    {"labels": {k: str(v)[:80] for k, v in (s.get("metric") or {}).items()},
                     "value": s.get("value") or s.get("values")}
                    for s in result[:10]
                ],
            }
            return summary, f"{len(result)} series (status {summary['status']})"

        return _read(tool, _Call(url, headers, secrets), summarize,
                     f"prometheus://query/{urllib.parse.quote(query, safe='')}")

    return _guard(tool, run)


def loki_query(
    query: str, *, start: str | None = None, end: str | None = None, limit: int = 100
) -> SignalReport:
    """Range query against a self-hosted Loki. Log lines are the most
    user-influenced text in the stack, so the wrapper matters most here."""
    tool = "loki_query"

    def run() -> SignalReport:
        if not str(query).strip():
            return SignalReport(tool=tool, status="error", detail="query is required")
        base = _resolve(LOKI_URL_ENV)
        if not base:
            return _skip(tool, LOKI_URL_ENV,
                         "point this at your Loki to pull log context for an "
                         "incident")
        params: dict[str, str] = {"query": query, "limit": str(max(1, min(limit, 1000)))}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        url = f"{base.rstrip('/')}/loki/api/v1/query_range?{urllib.parse.urlencode(params)}"
        headers, secrets = _optional_bearer(LOKI_TOKEN_ENV)

        def summarize(payload: dict):
            streams = ((payload.get("data") or {}).get("result")) or []
            lines = []
            for stream in streams[:5]:
                for _ts, line in (stream.get("values") or [])[:10]:
                    lines.append(str(line)[:300])
            summary = {
                "query": str(query)[:300],
                "stream_count": len(streams),
                "line_count": sum(len(s.get("values") or []) for s in streams),
                "lines": lines,
            }
            return summary, (f"{summary['line_count']} line(s) across "
                             f"{len(streams)} stream(s)")

        return _read(tool, _Call(url, headers, secrets), summarize,
                     f"loki://query/{urllib.parse.quote(query, safe='')}")

    return _guard(tool, run)


def jaeger_query_trace(trace_id: str) -> SignalReport:
    """Fetch one trace by id from a self-hosted Jaeger."""
    tool = "jaeger_query_trace"

    def run() -> SignalReport:
        if not str(trace_id).strip():
            return SignalReport(tool=tool, status="error",
                                detail="trace_id is required")
        base = _resolve(JAEGER_URL_ENV)
        if not base:
            return _skip(tool, JAEGER_URL_ENV,
                         "point this at your Jaeger query service to resolve "
                         "trace ids")
        url = (f"{base.rstrip('/')}/api/traces/"
               f"{urllib.parse.quote(str(trace_id), safe='')}")
        headers, secrets = _optional_bearer(JAEGER_TOKEN_ENV)

        def summarize(payload: dict):
            traces = payload.get("data") or []
            spans = traces[0].get("spans") if traces else []
            spans = spans or []
            errors = [
                s for s in spans
                if any(t.get("key") == "error" and t.get("value")
                       for t in (s.get("tags") or []))
            ]
            summary = {
                "trace_id": str(trace_id),
                "span_count": len(spans),
                "error_span_count": len(errors),
                "duration_us": sum(int(s.get("duration") or 0) for s in spans),
                "operations": [str(s.get("operationName", ""))[:120] for s in spans[:15]],
            }
            return summary, (f"trace {trace_id}: {len(spans)} span(s), "
                             f"{len(errors)} with an error tag")

        return _read(tool, _Call(url, headers, secrets), summarize,
                     f"jaeger://traces/{trace_id}")

    return _guard(tool, run)


READERS = {
    "sentry_get_issue": sentry_get_issue,
    "datadog_query_metrics": datadog_query_metrics,
    "pagerduty_get_incident": pagerduty_get_incident,
    "prometheus_query": prometheus_query,
    "loki_query": loki_query,
    "jaeger_query_trace": jaeger_query_trace,
}
