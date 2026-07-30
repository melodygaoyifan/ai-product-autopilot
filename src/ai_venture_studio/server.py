"""Webhook mode (§09.5) — the always-on entry points.

FastAPI receives GitHub PR events and GitLab MR events (Gate 1 entry)
and incident POSTs (Gate 6 entry) and launches the same CLI pipelines in
detached worker processes; results land in the usual mirrors and on the
forge. The SQLite checkpointer gives crash-resumability per review.

Honest scope note (§08.2.2.12): the design's production posture is
Celery + Redis supervising LangGraph for failure detection across
instances. This single-process server is the CLI-parity webhook surface;
the Celery supervisor is additive when multi-instance operation matters.

Security: GitHub webhooks are verified with HMAC-SHA256
(AUTOPRODUCT_WEBHOOK_SECRET). Unsigned or mis-signed deliveries are
rejected before any parsing of the payload.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request

REVIEW_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}
# GitLab MR actions that mean "there is something new to review". `update`
# is additionally gated on oldrev (new commits) at the route.
GITLAB_REVIEW_ACTIONS = {"open", "reopen", "update"}


def _jobs_path(repo_dir: str) -> Path:
    return Path(repo_dir) / ".mas" / "jobs.yaml"


def _record_job(repo_dir: str, pid: int, args: list[str]) -> None:
    path = _jobs_path(repo_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    jobs = (yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else []) or []
    jobs = jobs[-200:]
    jobs.append({"pid": pid, "args": args, "status": "running"})
    path.write_text(yaml.safe_dump(jobs, sort_keys=False), encoding="utf-8")


def _reconcile_jobs(repo_dir: str) -> list[dict]:
    """Lightweight supervision: a 'running' job whose pid is gone is marked
    finished (its artifacts tell the real story) — and reviews that died
    mid-flight remain resumable via their SQLite checkpoints. The Celery
    supervisor stays the multi-instance upgrade path."""
    from ai_venture_studio.procs import pid_alive

    path = _jobs_path(repo_dir)
    if not path.exists():
        return []
    jobs = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    changed = False
    for job in jobs:
        if job.get("status") == "running":
            try:
                pid = int(job["pid"])
            except (TypeError, ValueError):
                pid = -1
            if not pid_alive(pid):
                job["status"] = "finished"
                changed = True
    if changed:
        path.write_text(yaml.safe_dump(jobs, sort_keys=False), encoding="utf-8")
    return jobs


def _spawn(args: list[str], repo_dir: str) -> int:
    """Dispatch work. Two modes:

    - AUTOPRODUCT_QUEUE_DB set → enqueue into the SQLite job queue; any
      number of `avs worker` processes drain it (multi-instance,
      burst-safe, restart-surviving). Returns the negated job id so
      callers can tell a queue ticket from a pid.
    - default → detached worker subprocess: the request cycle never
      blocks on a review. Deliberate exception to the subprocess
      timeout/capture convention: a worker outlives the request by
      design, its output lands in the `.mas/` mirrors, and its lifecycle
      belongs to the OS.
    """
    queue_db = os.environ.get("AUTOPRODUCT_QUEUE_DB", "")
    if queue_db:
        from ai_venture_studio.jobqueue import enqueue

        return -enqueue(queue_db, args[0], args)
    # Detach so a worker outlives the request: setsid on POSIX, its own
    # process group + no console on Windows (start_new_session is POSIX-only).
    detach: dict = (
        {"start_new_session": True}
        if os.name != "nt"
        else {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
        }
    )
    proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
        [sys.executable, "-m", "ai_venture_studio.cli", *args],
        cwd=repo_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **detach,
    )
    _record_job(repo_dir, proc.pid, args)
    return proc.pid


def _verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header.removeprefix("sha256="), expected)


_REVIEW_ID = re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z")


def create_app(repo_dir: str = ".", *, spawn=_spawn) -> FastAPI:
    app = FastAPI(title="ai-venture-studio", docs_url=None, redoc_url=None)
    repo = str(Path(repo_dir).resolve())

    from ai_venture_studio import tenants as tenants_mod

    # Multi-tenant mode is the presence of the registry, nothing more
    # (ADR-030). Loading validates it; an invalid registry must fail at
    # startup rather than serve half of it.
    tenant_list = tenants_mod.load_tenants(repo)

    def _bearer(request: Request) -> str:
        auth = request.headers.get("Authorization", "")
        return auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else ""

    def _workspace(request: Request) -> str:
        """The one workspace this request may touch.

        Single-tenant: the served repo, shared-secret authenticated as
        before. Multi-tenant: resolved from the caller's token, never from
        a client-supplied path or id.
        """
        if not tenant_list:
            secret = os.environ.get("AUTOPRODUCT_WEBHOOK_SECRET")
            if not secret:
                raise HTTPException(503, "AUTOPRODUCT_WEBHOOK_SECRET is not configured")
            if not hmac.compare_digest(_bearer(request), secret):
                raise HTTPException(401, "missing or invalid bearer token")
            return repo
        tenant = tenants_mod.resolve_tenant(tenant_list, _bearer(request))
        if tenant is None:
            # One message for unknown, disabled, and absent tokens: the
            # response never says which tenants exist.
            raise HTTPException(401, "missing or invalid tenant token")
        try:
            return str(tenants_mod.tenant_workspace(tenant))
        except tenants_mod.TenantError as exc:
            raise HTTPException(503, str(exc)) from exc

    def _read_workspace(request: Request) -> str:
        """Workspace for a read route. Single-tenant keeps its existing
        open-read posture (a localhost dashboard); multi-tenant requires the
        token, because one tenant must never enumerate another's reviews."""
        if not tenant_list:
            return repo
        return _workspace(request)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "tenants": len(tenant_list) or None}

    def _webhook_auth(tenant_id: str | None, route: str) -> tuple[str, str]:
        """(secret, workspace) for a forge webhook delivery. Forge deliveries
        carry no bearer token, so the secret must be per-tenant and the
        tenant is named in the path. The path only SELECTS which secret must
        verify — it grants nothing on its own. Shared by every forge route;
        only the verification scheme differs per forge."""
        if tenant_list:
            if tenant_id is None:
                raise HTTPException(
                    404, f"multi-tenant mode: post to {route}/<tenant_id>"
                )
            tenant = next(
                (t for t in tenant_list if t.id == tenant_id and t.enabled), None
            )
            secret = None
            if tenant is not None:
                try:
                    secret = tenant.webhook_secret()
                except Exception as exc:  # noqa: BLE001 — unset ref is fatal
                    raise HTTPException(503, str(exc)) from exc
            if secret is None:
                # Same response for unknown tenant and unconfigured secret.
                raise HTTPException(401, "invalid webhook signature")
            workspace = str(tenants_mod.tenant_workspace(tenant))
        else:
            if tenant_id is not None:
                raise HTTPException(404, f"single-tenant mode: post to {route}")
            secret = os.environ.get("AUTOPRODUCT_WEBHOOK_SECRET")
            if not secret:
                raise HTTPException(503, "AUTOPRODUCT_WEBHOOK_SECRET is not configured")
            workspace = repo
        return secret, workspace

    @app.post("/webhook/github", status_code=202)
    @app.post("/webhook/github/{tenant_id}", status_code=202)
    async def github_webhook(request: Request, tenant_id: str | None = None):
        secret, workspace = _webhook_auth(tenant_id, "/webhook/github")
        body = await request.body()
        if not _verify_signature(
            secret, body, request.headers.get("X-Hub-Signature-256")
        ):
            raise HTTPException(401, "invalid webhook signature")

        event = request.headers.get("X-GitHub-Event", "")
        payload = json.loads(body or b"{}")
        if event != "pull_request" or payload.get("action") not in REVIEW_ACTIONS:
            return {"queued": False, "reason": f"ignored event {event}/{payload.get('action')}"}

        pr_url = payload.get("pull_request", {}).get("html_url")
        if not pr_url:
            raise HTTPException(422, "payload has no pull_request.html_url")
        pid = spawn(["review", pr_url], workspace)
        return {"queued": True, "target": pr_url, "worker_pid": pid}

    @app.post("/webhook/gitlab", status_code=202)
    @app.post("/webhook/gitlab/{tenant_id}", status_code=202)
    async def gitlab_webhook(request: Request, tenant_id: str | None = None):
        # GitLab authenticates with a plain shared secret in X-Gitlab-Token
        # (equality, not an HMAC of the body — that is GitLab's design, not
        # an omission here); compare constant-time before any parsing.
        secret, workspace = _webhook_auth(tenant_id, "/webhook/gitlab")
        token = request.headers.get("X-Gitlab-Token", "")
        if not (token and hmac.compare_digest(token, secret)):
            raise HTTPException(401, "invalid webhook token")
        body = await request.body()
        payload = json.loads(body or b"{}")
        if payload.get("object_kind") != "merge_request":
            return {
                "queued": False,
                "reason": f"ignored event {payload.get('object_kind')}",
            }
        attrs = payload.get("object_attributes") or {}
        action = attrs.get("action")
        if action not in GITLAB_REVIEW_ACTIONS:
            return {"queued": False, "reason": f"ignored action {action}"}
        if action == "update" and not attrs.get("oldrev"):
            # Only pushes carry oldrev; title/label/assignee edits arrive as
            # `update` too, and re-reviewing on every metadata touch would
            # spam the MR with duplicate reviews.
            return {"queued": False, "reason": "update without new commits"}
        mr_url = attrs.get("url")
        if not mr_url:
            raise HTTPException(422, "payload has no object_attributes.url")
        pid = spawn(["review", mr_url], workspace)
        return {"queued": True, "target": mr_url, "worker_pid": pid}

    @app.get("/metrics")
    async def metrics():
        # Prometheus text; aggregate-only by construction (same fields as
        # the opt-in telemetry payload — doc 09 §10, plan phase C).
        from fastapi.responses import PlainTextResponse

        from ai_venture_studio.observability import prometheus_metrics

        return PlainTextResponse(prometheus_metrics(repo))

    def _translate_signal(source: str, payload: dict) -> dict:
        """Named monitoring webhooks → the /incidents shape (doc 09 §12).
        Each source's fields are mapped, and a dedupe_key is derived so a
        re-fired alert updates instead of multiplying."""
        if source == "sentry":
            event = payload.get("event") or payload
            issue_id = str(
                payload.get("issue_id")
                or (payload.get("issue") or {}).get("id")
                or event.get("issue_id")
                or ""
            )
            return {"title": str(event.get("title") or payload.get("message", "sentry event"))[:200],
                    "kind": "error", "source": "sentry",
                    # The signal reader resolves this later, if a token exists.
                    "external_id": issue_id,
                    "dedupe_key": str(payload.get("id") or event.get("event_id") or "")}
        if source == "datadog":
            return {"title": str(payload.get("title", "datadog monitor"))[:200],
                    "kind": str(payload.get("alert_type", "alert")),
                    "source": "datadog",
                    "dedupe_key": str(payload.get("alert_id") or payload.get("id") or "")}
        return {"title": str(payload.get("incident", {}).get("title")
                             or payload.get("summary", "pagerduty incident"))[:200],
                "kind": "incident", "source": "pagerduty",
                "dedupe_key": str(payload.get("incident", {}).get("id") or "")}

    @app.post("/webhooks/{source}", status_code=202)
    async def monitoring_webhook(source: str, request: Request):
        if source not in ("sentry", "datadog", "pagerduty"):
            raise HTTPException(404, f"unknown signal source {source!r}")
        workspace = _workspace(request)
        incident = _translate_signal(source, await request.json())
        inbox = Path(workspace) / ".mas" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        dedupe = incident.get("dedupe_key")
        if dedupe:
            marker = inbox / f".seen-{source}-{dedupe}"
            if marker.exists():
                return {"status": "deduplicated", "dedupe_key": dedupe}
            marker.write_text("")
        incident_id = uuid.uuid4().hex[:12]
        (inbox / f"{incident_id}.yaml").write_text(
            yaml.safe_dump({"id": incident_id, **incident}, sort_keys=False))
        return {"status": "accepted", "id": incident_id}

    @app.post("/incidents", status_code=202)
    async def incidents(request: Request):
        # Same trust bar as the GitHub webhook (PR #16 self-review finding):
        # incident intake mutates state and spawns work — bearer-token
        # authenticated, and in multi-tenant mode the token also picks the
        # workspace.
        workspace = _workspace(request)
        payload = await request.json()
        title = str(payload.get("title", "")).strip()
        if not title:
            raise HTTPException(422, "incident needs a title")
        incident_id = uuid.uuid4().hex[:12]
        inbox = Path(workspace) / ".mas" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        path = inbox / f"{incident_id}.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "id": incident_id,
                    "title": title,
                    "body": str(payload.get("body", "")),
                    "source": str(payload.get("source", "webhook")),
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        pid = spawn(["triage", str(path)], workspace)
        return {"queued": True, "incident_id": incident_id, "worker_pid": pid}

    @app.get("/jobs")
    def jobs(request: Request):
        # Read routes are tenant-scoped too: job argv carries PR URLs and
        # workspace paths, so an unauthenticated listing would leak one
        # tenant's work to another.
        return _reconcile_jobs(_read_workspace(request))

    @app.get("/reviews")
    def reviews(request: Request, limit: int = 50):
        # Sync handler (FastAPI threadpool) + bounded, newest-first listing
        # (PR #16 self-review: unbounded scan per request).
        reviews_dir = Path(_read_workspace(request)) / ".mas" / "reviews"
        if not reviews_dir.is_dir():
            return []
        rows = []
        newest_first = sorted(
            (d for d in reviews_dir.iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )[: max(1, min(limit, 500))]
        for review_dir in newest_first:
            final = sorted(review_dir.glob("[0-9]*-final.yaml"))
            if final:
                data = yaml.safe_load(final[-1].read_text(encoding="utf-8")) or {}
                rows.append(
                    {
                        "review_id": review_dir.name,
                        "verdict": data.get("verdict"),
                        "target": data.get("target"),
                        "finished_at": data.get("written_at"),
                    }
                )
            elif review_dir.is_dir():
                rows.append({"review_id": review_dir.name, "verdict": None})
        return rows

    @app.get("/reviews/{review_id}")
    def review_detail(request: Request, review_id: str):
        from ai_venture_studio.replay import load_replay, summarize_step

        # review_id lands in a filesystem path: anything but an opaque id is
        # a traversal attempt, and in multi-tenant mode it would be a
        # traversal into another tenant's workspace.
        if not _REVIEW_ID.match(review_id):
            raise HTTPException(422, "review_id must match [A-Za-z0-9_-]{1,64}")
        try:
            rep = load_replay(
                Path(_read_workspace(request)) / ".mas" / "reviews", review_id
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {
            "review_id": rep.review_id,
            "verdict": rep.verdict,
            "duration_s": rep.duration_s,
            "steps": [
                {"node": s.node, "at": s.written_at.isoformat(), "summary": summarize_step(s)}
                for s in rep.steps
            ],
        }

    return app


def serve(repo_dir: str = ".", host: str = "127.0.0.1", port: int = 8422) -> None:
    import threading

    import uvicorn

    def _recover():
        from ai_venture_studio.deploy import recover_deploy_reviews
        from ai_venture_studio.maintenance import recover_maintenance
        from ai_venture_studio.orchestrator import recover_reviews

        for r in recover_reviews(repo_dir):
            print(f"[recover] review {r['review_id']}: {r['status']}")
        for r in recover_deploy_reviews(repo_dir) + recover_maintenance(repo_dir):
            print(f"[recover] {r['kind']} {r['id']}: {r['status']}")

    threading.Thread(target=_recover, daemon=True).start()
    uvicorn.run(create_app(repo_dir), host=host, port=port, log_level="info")
