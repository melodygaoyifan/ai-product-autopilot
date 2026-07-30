"""Founder Studio — the browser UI for the FDR flow.

`avs studio --repo-dir <workspace>` serves a single-page flow on
localhost: edit the FDR, get questions or the plain-language confirmation,
press the build button instead of typing --yes, watch progress, read the
build report. All state lives in the same workspace files the CLI writes —
the Studio is a veneer, never a second source of truth.

Local-first: binds 127.0.0.1, no external assets, no accounts. The build
runs as the same detached worker the CLI uses.

Every user-facing string comes from `studio_i18n` so `--lang en` renders the
whole flow in English. The default stays the original bilingual Chinese-first
text, so nothing changes for existing users.

Different users get different modes (`studio_modes`): founder is the
original UI unchanged; engineer and enterprise append read-only cards. The
mode resolves from the workspace's edition, `--mode` overrides, and a mode
may only ADD visibility — never remove a form or a required action.
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ai_venture_studio.studio_i18n import DEFAULT_LANGUAGE, normalize, t
from ai_venture_studio.studio_modes import (
    MODES,
    StudioModeError,
    engineer_panel,
    enterprise_panel,
    mode_strip,
    resolve_mode,
    review_timeline_body,
)

_STYLE = """
body{font-family:-apple-system,'PingFang SC',sans-serif;max-width:760px;
margin:2rem auto;padding:0 1rem;line-height:1.6;color:#1a1a1a}
textarea{width:100%;min-height:340px;font:14px/1.5 inherit;padding:.8rem;
border:1px solid #ccc;border-radius:8px;box-sizing:border-box}
button{background:#07c160;color:#fff;border:0;border-radius:8px;
padding:.7rem 1.6rem;font-size:1rem;cursor:pointer}
button.secondary{background:#576b95}
pre{white-space:pre-wrap;background:#f7f7f7;padding:1rem;border-radius:8px}
.card{border:1px solid #e5e5e5;border-radius:10px;padding:1rem 1.2rem;
margin:1rem 0}
.muted{color:#888;font-size:.9rem}
h1{font-size:1.4rem}
.ok{color:#07c160}.warn{color:#c87d2f}.bad{color:#d23}
table{border-collapse:collapse;width:100%}
td{padding:.25rem .6rem;border-bottom:1px solid #eee;font-size:.9rem;
text-align:left;vertical-align:top}
"""


def _md(path: Path) -> str:
    return html.escape(path.read_text(encoding="utf-8")) if path.exists() else ""


# Inline SVG favicon: kills the /favicon.ico 404 in every console (the
# first thing a browser-driven evaluation sees) without adding a route or
# an asset file.
_FAVICON = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E"
    "%3Ctext y='13' font-size='13'%3E%F0%9F%8F%97%3C/text%3E%3C/svg%3E"
)


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>"
        f"<link rel='icon' href=\"{_FAVICON}\">"
        f"<style>{_STYLE}</style><body><h1>{html.escape(title)}</h1>{body}"
    )


def _failed_tasks(root: Path) -> list[str]:
    path = root / "product" / "outcomes.yaml"
    if not path.exists():
        return []
    outcomes = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [o["task_id"] for o in outcomes if o.get("status") != "built"]


def _pending_feature(root: Path) -> Path | None:
    features_dir = root / "product" / "features"
    if not features_dir.is_dir():
        return None
    for d in sorted(features_dir.iterdir(), reverse=True):
        if (d / "CONFIRMATION.md").exists() and not (d / "REPORT.md").exists():
            return d
    return None


def _build_running(root: Path) -> bool:
    marker = root / ".mas" / "build.pid"
    if not marker.exists():
        return False
    try:
        pid = int(marker.read_text().strip())
    except ValueError:
        return False
    from ai_venture_studio.procs import pid_alive

    return pid_alive(pid)


_STATE_ICON = {"built": "✅", "pending": "⏳"}
# Same shape the server's review routes enforce — a review id is a path
# segment, so anything else is a traversal attempt, not a typo.
_REVIEW_ID = re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z")


def _task_states(root: Path) -> list[dict]:
    """Per-task build state from the workspace files the CLI writes (the
    Studio is a veneer, never a second source of truth): a spec gains
    `built: true` as the run progresses — its `(task:<id>)` request marker
    links it back to the plan — and outcomes.yaml records failures when a
    run finishes."""
    plan_path = root / "product" / "plan.yaml"
    if not plan_path.exists():
        return []
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    from ai_venture_studio.upstream.plan import built_task_ids

    built_ids = built_task_ids(root)  # one definition of "built", shared
    failed: dict[str, str] = {}
    outcomes_path = root / "product" / "outcomes.yaml"
    if outcomes_path.exists():
        for o in yaml.safe_load(outcomes_path.read_text(encoding="utf-8")) or []:
            if o.get("status") != "built" and o.get("task_id"):
                failed[o["task_id"]] = str(o.get("status", "failed"))
    # `pending` covers everything from "not started" to "on its third build
    # attempt", which is most of a run's wall-clock. The step journal is the
    # difference between the two — still a read of a file the CLI writes.
    from ai_venture_studio.upstream import progress as progress_journal

    steps = progress_journal.latest_by_task(root)
    return [
        {
            "id": t["id"],
            "title": t.get("title", t["id"]),
            "state": "built" if t["id"] in built_ids
            else failed.get(t["id"], "pending"),
            "step": str(steps.get(t["id"], {}).get("detail", "")),
        }
        for t in plan.get("tasks", [])
    ]


def _progress(root: Path) -> dict:
    plan_path = root / "product" / "plan.yaml"
    total = built = 0
    if plan_path.exists():
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
        total = len(plan.get("tasks", []))
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=root, capture_output=True, timeout=60, text=True
    ).stdout
    built = log.count("feat(")
    return {
        "total": total,
        "built": built,
        "running": _build_running(root),
        "tasks": _task_states(root),
    }


def _task_list_html(tasks: list[dict]) -> str:
    return "".join(
        f"<li id='task-{html.escape(t['id'])}'>"
        f"{_STATE_ICON.get(t['state'], '❌')} {html.escape(t['title'])}"
        f"{'' if t['state'] in _STATE_ICON else ' <span class=bad>(' + html.escape(t['state']) + ')</span>'}"
        # The step only means anything while the task is still in flight; on a
        # built task it is stale narration of something already finished.
        + (
            f" <span class=muted>— {html.escape(t['step'])}</span>"
            if t.get("step") and t["state"] == "pending"
            else ""
        )
        + "</li>"
        for t in tasks
    )


def create_studio_app(
    repo_dir: str | Path, *, spawn=None, provider: str = "anthropic",
    lang: str = DEFAULT_LANGUAGE, mode: str | None = None,
) -> FastAPI:
    root = Path(repo_dir).resolve()
    lang = normalize(lang)
    # --mode / edition only set the DEFAULT; the user switches per request
    # (adaptable, never adaptive — the UI must not flip modes on its own).
    default_mode = resolve_mode(root, mode)

    def _(key: str) -> str:
        """This page's string in the chosen language (studio_i18n)."""
        return t(lang, key)

    def _req_mode(request: Request) -> str:
        """Query beats cookie beats the startup default. An unknown ?mode=
        is a loud 400, same policy as an unknown --mode."""
        query = request.query_params.get("mode")
        if query:
            try:
                return resolve_mode(root, query)
            except StudioModeError as exc:
                raise HTTPException(400, str(exc)) from exc
        cookie = request.cookies.get("studio_mode")
        if cookie in MODES:
            return cookie
        return default_mode

    # The three handlers below run LLM calls for minutes. `/build` and
    # `/retry` already refused to start a second worker; these did not, and a
    # button that looks dead for six minutes is a button people press twice —
    # two autopilots on one workspace race on git and on the same files. The
    # flag is in-process because the Studio is one localhost process.
    thinking: dict[str, str] = {}

    def _thinking_page(request: Request, what: str) -> HTMLResponse:
        return _render(
            request, _("title_working"),
            f"<div class=card><b class=warn>{_('working_lead')}</b>"
            f"<p>{html.escape(what)}</p>"
            f"<p class=muted>{_('working_hint')}</p></div>"
            "<script>setTimeout(()=>location.href='/',15000)</script>",
        )

    def _failure_page(request: Request, exc: Exception) -> HTMLResponse:
        """A founder should never meet a stack trace, and should never be
        told nothing either: plain language first, the real error one click
        away, and the workspace left where they can retry."""
        return _render(
            request, _("title_failed"),
            f"<div class=card><b class=bad>{_('failed_lead')}</b>"
            f"<p>{_('failed_hint')}</p>"
            f"<details><summary class=muted>{_('failed_detail')}</summary>"
            f"<pre>{html.escape(f'{type(exc).__name__}: {exc}')}</pre>"
            "</details></div>"
            f"<p><a href='/'>{_('link_back')}</a></p>",
        )

    def _render(request: Request, title: str, body: str) -> HTMLResponse:
        """Every page: the visible mode strip, the page body, then the
        mode's read-only cards. Founder mode appends no cards, so the
        founder flow stays exactly the pre-mode UI plus the switcher.
        Panels are built per request — they reflect the workspace files as
        of this page load, never a cached copy."""
        req_mode = _req_mode(request)
        body = mode_strip(req_mode, _) + body
        if req_mode == "engineer":
            body += engineer_panel(root, _, _task_states(root))
        elif req_mode == "enterprise":
            body += enterprise_panel(root, _)
        response = _page(title, body)
        if request.query_params.get("mode"):
            # An explicit switch persists across the POST→redirect cycle.
            response.set_cookie("studio_mode", req_mode)
        return response

    app = FastAPI(
        title="avs studio", docs_url=None, redoc_url=None, openapi_url=None
    )

    # Shared-machine / corp deployment: AVS_STUDIO_TOKEN (env or *_FILE
    # mount) gates every request. Absent token keeps the original
    # localhost-only posture; the CLI refuses to bind non-loopback without
    # one. This is deliberately a shared secret, not SSO — the documented
    # upgrade path is OIDC in front (reverse proxy), not a home-grown login.
    from ai_venture_studio.secrets import env_or_file

    studio_token = env_or_file("AVS_STUDIO_TOKEN")

    @app.middleware("http")
    async def token_gate(request: Request, call_next):
        if not studio_token:
            return await call_next(request)
        import hmac as _hmac

        auth = request.headers.get("Authorization", "")
        supplied = (
            request.cookies.get("studio_token")
            or request.query_params.get("token")
            or (auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else "")
        )
        if not (supplied and _hmac.compare_digest(supplied, studio_token)):
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse(
                "This Studio requires its access token. Open "
                "/?token=<AVS_STUDIO_TOKEN> once — a cookie keeps you "
                "signed in after that.",
                status_code=401,
            )
        response = await call_next(request)
        if request.query_params.get("token"):
            response.set_cookie(
                "studio_token", studio_token, httponly=True, samesite="lax"
            )
        return response

    @app.middleware("http")
    async def same_origin_guard(request: Request, call_next):
        """Localhost is not a security boundary against the browser: a
        malicious page can form-POST to 127.0.0.1 (sweep finding). POSTs
        must come from the Studio itself — compared against the request's
        OWN host, so a Studio served on a corp hostname keeps working
        (hardcoding localhost here broke every POST behind a real name)."""
        if request.method == "POST":
            origin = request.headers.get("origin") or request.headers.get("referer") or ""
            if origin:
                from urllib.parse import urlsplit

                origin_host = urlsplit(origin).hostname or ""
                own_host = request.url.hostname or ""
                if origin_host not in (own_host, "127.0.0.1", "localhost"):
                    from fastapi.responses import PlainTextResponse

                    return PlainTextResponse(
                        "cross-origin POST rejected", status_code=403
                    )
        return await call_next(request)

    def _spawn_build() -> int:
        if spawn is not None:
            return spawn(root)
        # The worker inherits the Studio's provider — without this, a Studio
        # started with --provider mock spawned a build that wanted a real
        # key and died silently. Its output goes to .mas/build.log, not
        # DEVNULL: a worker that dies before writing the report must leave
        # forensics behind.
        (root / ".mas").mkdir(exist_ok=True)
        log = (root / ".mas" / "build.log").open("ab")
        proc = subprocess.Popen(  # noqa: S603 — fixed argv
            [sys.executable, "-m", "ai_venture_studio.cli", "create", str(root),
             "--profile", _profile(root), "--provider", provider, "--yes"],
            cwd=root, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        (root / ".mas" / "build.pid").write_text(str(proc.pid), encoding="utf-8")
        return proc.pid

    def _profile(workspace: Path) -> str:
        data = yaml.safe_load(
            (workspace / ".mas" / "project.yaml").read_text(encoding="utf-8")
        )
        return data["profile"]

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        fdr = root / "FDR.md"
        report = root / "product" / "BUILD-REPORT.md"
        confirmation = root / "product" / "CONFIRMATION.md"
        questions = root / "FDR-QUESTIONS.md"
        progress = _progress(root)

        if progress["running"]:
            tasks = progress["tasks"]
            done = sum(1 for t in tasks if t["state"] == "built") or progress["built"]
            total = progress["total"] or "?"
            checklist = (
                f"<ul id=tasks style='list-style:none;padding-left:0'>"
                f"{_task_list_html(tasks)}</ul>"
                if tasks
                else f"<p class=muted id=tasks>{_('planning')}</p>"
            )
            # Live per-task progress (signal s3: "it looks frozen while it
            # works") — poll /status, update in place, one full reload when
            # the worker exits so the report page takes over.
            return _render(
                request, _("title_building"),
                f"<div class=card><p>{_('done_label')} <b id=done>{done}</b> / "
                f"<b id=total>{total}</b> {_('updates_live')}</p>"
                f"{checklist}</div>"
                "<script>\n"
                "const ICONS={built:'✅',pending:'⏳'};\n"
                "async function poll(){try{\n"
                "  const s=await (await fetch('/status')).json();\n"
                "  if(!s.running){location.reload();return}\n"
                "  const built=s.tasks.filter(t=>t.state==='built').length;\n"
                "  document.getElementById('done').textContent=built||s.built;\n"
                "  if(s.total)document.getElementById('total').textContent=s.total;\n"
                "  for(const t of s.tasks){\n"
                "    const li=document.getElementById('task-'+t.id);\n"
                "    if(li)li.textContent=(ICONS[t.state]||'❌')+' '+t.title\n"
                "      +(ICONS[t.state]?'':' ('+t.state+')')\n"
                "      +((t.step&&t.state==='pending')?' — '+t.step:'');\n"
                "  }\n"
                "}catch(e){}setTimeout(poll,5000)}\n"
                "poll();\n"
                "setTimeout(()=>location.reload(),120000)\n"
                "</script>",
            )
        interrupted = (
            (root / ".mas" / "build.pid").exists()
            and not report.exists()
            and progress["tasks"]
        )
        if interrupted:
            tasks = progress["tasks"]
            unbuilt = [t for t in tasks if t["state"] != "built"]
            retries = "".join(
                f"<form method=post action=/retry style='display:inline'>"
                f"<input type=hidden name=task_id value='{html.escape(task['id'])}'>"
                f"<button class=secondary>{_('btn_resume')} "
                f"{html.escape(task['title'])}</button></form> "
                for task in unbuilt
            )
            done_note = (
                f"<p class=ok>{_('interrupted_all_done')}</p>"
                if not unbuilt
                else f"<p>{_('interrupted_resume')}</p>" + retries
            )
            return _render(
                request, _("title_interrupted"),
                f"<div class=card><b class=warn>{_('interrupted_lead')}"
                f"</b><ul style='list-style:none;padding-left:0'>"
                f"{_task_list_html(tasks)}</ul>{done_note}</div>"
                "<form method=post action=/reset style='margin-top:1rem'>"
                f"<button class=secondary>{_('btn_edit_and_restart')}"
                "</button></form>",
            )
        if report.exists():
            features_dir = root / "product" / "features"
            feature_cards = ""
            if features_dir.is_dir():
                for d in sorted(features_dir.iterdir()):
                    state = (
                        _("state_done") if (d / "REPORT.md").exists()
                        else (_("state_pending_confirm")
                              if (d / "CONFIRMATION.md").exists() else "…")
                    )
                    feature_cards += f"<div class=card>{html.escape(d.name)} — {state}</div>"
            pending = _pending_feature(root)
            if pending:
                return _render(
                    request, _("title_confirm_feature"),
                    f"<pre>{_md(pending / 'CONFIRMATION.md')}</pre>"
                    f"<form method=post action=/feature/build>"
                    f"<input type=hidden name=slug value='{html.escape(pending.name)}'>"
                    f"<button>{_('btn_build_feature')}</button></form>",
                )
            shots_dir = root / "product" / "screenshots"
            gallery = ""
            if shots_dir.is_dir():
                images = "".join(
                    f"<img src='/shots/{p.name}' style='max-width:100%;"
                    f"border:1px solid #ddd;border-radius:8px;margin:.4rem 0'>"
                    for p in sorted(shots_dir.glob("*.png"))
                )
                if images:
                    gallery = f"<h2>{_('h_screenshots')}</h2>{images}"
            acceptance = (
                f"<p><a href='/acceptance'>{_('link_acceptance')}</a></p>"
                if (root / "product" / "ACCEPTANCE.md").exists()
                else ""
            )
            failed = _failed_tasks(root)
            retry_block = ""
            if failed:
                rows = "".join(
                    f"<form method=post action=/retry style='display:inline'>"
                    f"<input type=hidden name=task_id value='{html.escape(failed_id)}'>"
                    f"<button class=secondary>{_('btn_retry')} "
                    f"{html.escape(failed_id)}</button></form> "
                    for failed_id in failed
                )
                retry_block = (
                    f"<div class=card><b class=warn>{_('failed_modules')}"
                    f"</b><p>{_('failed_hint')}</p>{rows}</div>"
                )
            no_features = f"<p class=muted>{_('first_version')}</p>"
            # Cost, in the founder's register, on the page they land on. Read
            # from the same ledger `avs cost` reads; the Studio stays a veneer.
            from ai_venture_studio import spend

            spent = spend.summarize_workspace(root)
            cost_card = (
                f"<div class=card><b>{_('h_cost')}</b>"
                f"<p>{html.escape(spend.render_plain(spent, what=_('cost_what')))}</p>"
                f"<p class=muted>{_('cost_own_key')}</p></div>"
                if spent.calls else ""
            )
            return _render(
                request, _("title_product"),
                f"<pre>{_md(report)}</pre>{acceptance}"
                f"<p><a href='/live'>🚀 {_('link_live')}</a></p>"
                f"{cost_card}{gallery}{retry_block}"
                f"<h2>{_('h_features')}</h2>"
                f"{feature_cards or no_features}"
                f"<h2>{_('h_broken')}</h2>"
                f"<p class=muted>{_('inc_hint')}</p>"
                "<form method=post action=/incident>"
                "<textarea name=description style='min-height:80px' "
                f"placeholder='{_('inc_placeholder')}'></textarea>"
                f"<p><button>{_('btn_incident')}</button></p></form>"
                f"<h2>{_('h_something_wrong')}</h2>"
                f"<p class=muted>{_('correction_hint')}</p>"
                + (
                    f"<details><summary class=muted>{_('correction_log')}"
                    f"</summary><pre>"
                    f"{_md(root / 'product' / 'CORRECTION-LOG.md')}"
                    "</pre></details>"
                    if (root / "product" / "CORRECTION-LOG.md").exists()
                    else ""
                ) +
                "<form method=post action=/correct>"
                "<textarea name=complaint style='min-height:80px' "
                f"placeholder='{_('correction_placeholder')}'></textarea>"
                f"<p><button>{_('btn_correct')}</button></p></form>"
                f"<h2>{_('h_add_feature')}</h2>"
                f"<p class=muted>{_('feature_hint')}</p>"
                "<form method=post action=/feature>"
                f"<textarea name=fdr placeholder='{_('feature_placeholder')}'></textarea>"
                f"<p><button>{_('btn_check_feature')}</button></p></form>"
                "<form method=post action=/undo style='margin-top:1.5rem'>"
                f"<button class=secondary>{_('btn_undo')}</button></form>",
            )
        if confirmation.exists():
            return _render(
                request, _("title_confirm_plan"),
                f"<pre>{_md(confirmation)}</pre>"
                f"<form method=post action=/build><button>{_('btn_start_building')}"
                "</button></form>"
                "<form method=post action=/reset style='margin-top:.5rem'>"
                f"<button class=secondary>{_('btn_edit_fdr')}</button></form>",
            )
        guide = _md(root / "FDR-GUIDE.md")
        question_block = (
            f"<div class=card><b class=warn>{_('answer_first')}"
            f"</b><pre>{_md(questions)}</pre></div>"
            if questions.exists()
            else ""
        )
        from ai_venture_studio.upstream.fdr import template_for

        current = (
            fdr.read_text(encoding="utf-8") if fdr.exists() else template_for(lang)
        )
        return _render(
            request, _("title_describe"),
            f"{question_block}"
            f"<form method=post action=/fdr>"
            f"<textarea name=fdr>{html.escape(current)}</textarea>"
            f"<p><button>{_('btn_check_and_plan')}</button></p>"
            f"</form>"
            f"<details><summary class=muted>{_('guide_summary')}"
            f"</summary><pre>{guide}</pre></details>",
        )

    @app.post("/fdr")
    async def save_fdr(request: Request):
        if "fdr" in thinking:
            return _thinking_page(request, thinking["fdr"])
        form = await request.form()
        (root / "FDR.md").write_text(str(form.get("fdr", "")), encoding="utf-8")
        for stale in ("FDR-QUESTIONS.md",):
            (root / stale).unlink(missing_ok=True)
        from starlette.concurrency import run_in_threadpool

        from ai_venture_studio.upstream.autopilot import run_autopilot

        thinking["fdr"] = _("working_fdr")
        try:
            # LLM calls block for minutes — off the event loop (sweep
            # finding), or the progress page can't even poll while the
            # assessor runs.
            await run_in_threadpool(
                run_autopilot, root, root / "FDR.md", yes=False, provider=provider
            )
        except Exception as exc:  # noqa: BLE001 — a founder gets a page, not a 500
            return _failure_page(request, exc)
        finally:
            thinking.pop("fdr", None)
        return RedirectResponse("/", status_code=303)

    @app.get("/acceptance", response_class=HTMLResponse)
    def acceptance(request: Request):
        return _render(
            request, _("title_acceptance"),
            f"<pre>{_md(root / 'product' / 'ACCEPTANCE.md')}</pre>"
            f"<p><a href='/'>{_('link_back')}</a></p>",
        )

    @app.get("/review/{review_id}", response_class=HTMLResponse)
    def review_detail(request: Request, review_id: str):
        """One review's mirror as a timeline — `avs replay` in the browser.
        Linked from the engineer card; reachable in every mode (modes add
        visibility, they never own a page)."""
        if not _REVIEW_ID.match(review_id):
            raise HTTPException(404)
        try:
            body = review_timeline_body(root, review_id, _)
        except FileNotFoundError:
            raise HTTPException(404) from None
        return _render(request, _("title_review"), body)

    @app.get("/shots/{name}")
    def shot(name: str):
        from fastapi.responses import FileResponse

        path = (root / "product" / "screenshots" / name).resolve()
        if not path.is_file() or path.parent != (root / "product" / "screenshots").resolve():
            raise HTTPException(404)
        return FileResponse(path)

    @app.post("/correct")
    async def correct(request: Request):
        if "correct" in thinking:
            return _thinking_page(request, thinking["correct"])
        form = await request.form()
        complaint = str(form.get("complaint", "")).strip()
        if complaint:
            from starlette.concurrency import run_in_threadpool

            from ai_venture_studio.upstream.correction import run_correction

            thinking["correct"] = _("working_correct")
            try:
                result = await run_in_threadpool(
                    run_correction, root, complaint, provider=provider
                )
            except Exception as exc:  # noqa: BLE001 — a page, never a 500
                return _failure_page(request, exc)
            finally:
                thinking.pop("correct", None)
            (root / "product" / "CORRECTION-LOG.md").open("a", encoding="utf-8").write(
                f"- {result.status}: {complaint[:120]} → {result.detail}\n"
            )
        return RedirectResponse("/", status_code=303)

    @app.post("/retry")
    async def retry(request: Request):
        form = await request.form()
        task_id = str(form.get("task_id", ""))
        if task_id and not _build_running(root):
            proc = subprocess.Popen(  # noqa: S603
                [sys.executable, "-m", "ai_venture_studio.cli", "retry-task", task_id,
                 "--repo-dir", str(root)],
                cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            (root / ".mas" / "build.pid").write_text(str(proc.pid), encoding="utf-8")
        return RedirectResponse("/", status_code=303)

    @app.post("/undo")
    def undo():
        from ai_venture_studio.upstream.autopilot import undo_last

        undo_last(root)
        return RedirectResponse("/", status_code=303)

    @app.post("/feature")
    async def feature(request: Request):
        if "feature" in thinking:
            return _thinking_page(request, thinking["feature"])
        form = await request.form()
        fdr_text = str(form.get("fdr", "")).strip()
        if fdr_text:
            fdr_path = root / ".mas" / "pending-feature.md"
            fdr_path.write_text(fdr_text, encoding="utf-8")
            from starlette.concurrency import run_in_threadpool

            from ai_venture_studio.upstream.autopilot import run_feature

            thinking["feature"] = _("working_feature")
            try:
                await run_in_threadpool(
                    run_feature, root, fdr_path, provider=provider, yes=False
                )
            except Exception as exc:  # noqa: BLE001 — a page, never a 500
                return _failure_page(request, exc)
            finally:
                thinking.pop("feature", None)
        return RedirectResponse("/", status_code=303)

    @app.post("/feature/build")
    async def feature_build(request: Request):
        form = await request.form()
        slug = str(form.get("slug", ""))
        feature_dir = root / "product" / "features" / slug
        if feature_dir.is_dir() and not _build_running(root):
            fdr_path = feature_dir / "fdr.md"
            if spawn is not None:
                spawn(root)
            else:
                log = (root / ".mas" / "build.log").open("ab")
                proc = subprocess.Popen(  # noqa: S603
                    [sys.executable, "-m", "ai_venture_studio.cli", "add", str(fdr_path),
                     "--repo-dir", str(root), "--provider", provider, "--yes"],
                    cwd=root, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                (root / ".mas" / "build.pid").write_text(str(proc.pid), encoding="utf-8")
        return RedirectResponse("/", status_code=303)

    @app.post("/build")
    def build():
        if not _build_running(root):
            _spawn_build()
        return RedirectResponse("/", status_code=303)

    @app.get("/live", response_class=HTMLResponse)
    def live(request: Request):
        from ai_venture_studio.studio_live import live_body

        return _render(request, _("title_live"), live_body(root, _, _profile(root)))

    @app.post("/live/guide")
    def live_guide():
        from ai_venture_studio.upstream.provisioning import write_cloud_guide

        write_cloud_guide(root, _profile(root))
        return RedirectResponse("/live", status_code=303)

    @app.post("/live/sweep")
    async def live_sweep(request: Request):
        from starlette.concurrency import run_in_threadpool

        from ai_venture_studio.studio_live import run_housekeeping

        try:
            await run_in_threadpool(run_housekeeping, root)
        except Exception as exc:  # noqa: BLE001 — a page, never a 500
            return _failure_page(request, exc)
        return RedirectResponse("/live", status_code=303)

    @app.post("/review/{review_id}/evidence")
    def review_evidence(request: Request, review_id: str):
        """The Gate-R artifact, one click from the review it attests. Same
        export as `avs evidence-bundle`; a human still attaches it to the
        CAB submission — the Studio never submits anything anywhere."""
        if not _REVIEW_ID.match(review_id):
            return RedirectResponse("/", status_code=303)
        from ai_venture_studio.adoption import write_evidence_bundle

        try:
            path = write_evidence_bundle(str(root), review_id)
        except FileNotFoundError as exc:
            return _render(
                request, _("title_evidence"),
                f"<div class=card><p class=bad>{html.escape(str(exc))}</p>"
                f"</div><p><a href='/'>{_('link_back')}</a></p>",
            )
        return _render(
            request, _("title_evidence"),
            f"<div class=card><b>{_('evidence_written')}</b>"
            f"<p><code>{html.escape(str(path))}</code></p>"
            f"<p class=muted>{_('evidence_note')}</p></div>"
            f"<p><a href='/review/{html.escape(review_id)}'>"
            f"{_('link_back')}</a></p>",
        )

    @app.post("/live/probe")
    async def live_probe(request: Request):
        # In the threadpool, not the event loop: a slow (or self-referential)
        # URL must never freeze every other Studio page for 8 seconds.
        from starlette.concurrency import run_in_threadpool

        from ai_venture_studio.studio_live import probe_live

        form = await request.form()
        await run_in_threadpool(probe_live, root, str(form.get("url", "")))
        return RedirectResponse("/live", status_code=303)

    @app.post("/incident")
    async def incident(request: Request):
        """It's broken → the real triage MAS. Same Incident model and
        artifacts as `avs triage`; only the front door is a textarea."""
        from starlette.concurrency import run_in_threadpool

        from ai_venture_studio.adoption import StageInactiveError, check_stage
        from ai_venture_studio.studio_live import incident_body, incident_intake

        form = await request.form()
        description = str(form.get("description", "")).strip()
        if not description:
            return RedirectResponse("/", status_code=303)
        try:
            check_stage(str(root), "maintenance")
        except StageInactiveError as exc:
            return _render(
                request, _("title_incident"),
                f"<div class=card><p class=bad>{html.escape(str(exc))}</p>"
                f"</div><p><a href='/'>{_('link_back')}</a></p>",
            )
        try:
            incident_obj, result = await run_in_threadpool(
                incident_intake, root, description, provider
            )
        except Exception as exc:  # noqa: BLE001 — a page, never a 500
            return _failure_page(request, exc)
        return _render(
            request, _("title_incident"), incident_body(_, incident_obj.id, result)
        )

    @app.post("/incident/fix")
    async def incident_fix(request: Request):
        from starlette.concurrency import run_in_threadpool

        from ai_venture_studio.studio_live import attempt_incident_fix, fix_body

        form = await request.form()
        incident_id = str(form.get("incident_id", ""))
        # Same shape rule as review ids — the id becomes a path segment.
        if not _REVIEW_ID.match(incident_id):
            return RedirectResponse("/", status_code=303)
        try:
            attempt = await run_in_threadpool(
                attempt_incident_fix, root, incident_id, provider
            )
        except Exception as exc:  # noqa: BLE001 — a page, never a 500
            return _failure_page(request, exc)
        return _render(request, _("title_fix"), fix_body(_, attempt))

    @app.post("/reset")
    def reset():
        for stale in (
            "product/CONFIRMATION.md",
            "product/BUILD-REPORT.md",
            "FDR-QUESTIONS.md",
            ".mas/build.pid",  # else an interrupted build's marker loops the page
        ):
            (root / stale).unlink(missing_ok=True)
        return RedirectResponse("/", status_code=303)

    @app.get("/status")
    def status():
        return JSONResponse(_progress(root))

    return app


def serve_studio(repo_dir: str | Path, host: str = "127.0.0.1", port: int = 8433,
                 *, provider: str = "anthropic",
                 lang: str = DEFAULT_LANGUAGE, mode: str | None = None) -> None:
    import uvicorn

    uvicorn.run(
        create_studio_app(repo_dir, provider=provider, lang=lang, mode=mode),
        host=host, port=port, log_level="warning",
    )
