"""Founder Studio — the browser UI for the FDR flow.

`autoproduct studio --repo-dir <workspace>` serves a single-page flow on
localhost: edit the FDR, get questions or the plain-language confirmation,
press the build button instead of typing --yes, watch progress, read the
build report. All state lives in the same workspace files the CLI writes —
the Studio is a veneer, never a second source of truth.

Local-first: binds 127.0.0.1, no external assets, no accounts. The build
runs as the same detached worker the CLI uses.

Every user-facing string comes from `studio_i18n` so `--lang en` renders the
whole flow in English. The default stays the original bilingual Chinese-first
text, so nothing changes for existing users.
"""

from __future__ import annotations

import html
import subprocess
import sys
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from autoproduct.studio_i18n import DEFAULT_LANGUAGE, normalize, t

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
"""


def _md(path: Path) -> str:
    return html.escape(path.read_text(encoding="utf-8")) if path.exists() else ""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>"
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
    try:
        import os

        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


_STATE_ICON = {"built": "✅", "pending": "⏳"}


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
    from autoproduct.upstream.plan import built_task_ids

    built_ids = built_task_ids(root)  # one definition of "built", shared
    failed: dict[str, str] = {}
    outcomes_path = root / "product" / "outcomes.yaml"
    if outcomes_path.exists():
        for o in yaml.safe_load(outcomes_path.read_text(encoding="utf-8")) or []:
            if o.get("status") != "built" and o.get("task_id"):
                failed[o["task_id"]] = str(o.get("status", "failed"))
    return [
        {
            "id": t["id"],
            "title": t.get("title", t["id"]),
            "state": "built" if t["id"] in built_ids
            else failed.get(t["id"], "pending"),
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
        f"</li>"
        for t in tasks
    )


def create_studio_app(
    repo_dir: str | Path, *, spawn=None, provider: str = "anthropic",
    lang: str = DEFAULT_LANGUAGE,
) -> FastAPI:
    root = Path(repo_dir).resolve()
    lang = normalize(lang)

    def _(key: str) -> str:
        """This page's string in the chosen language (studio_i18n)."""
        return t(lang, key)

    app = FastAPI(
        title="autoproduct studio", docs_url=None, redoc_url=None, openapi_url=None
    )

    @app.middleware("http")
    async def same_origin_guard(request: Request, call_next):
        """Localhost is not a security boundary against the browser: a
        malicious page can form-POST to 127.0.0.1 (sweep finding). POSTs
        must come from the Studio itself."""
        if request.method == "POST":
            origin = request.headers.get("origin") or request.headers.get("referer") or ""
            if origin and not origin.startswith(("http://127.0.0.1", "http://localhost")):
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("cross-origin POST rejected", status_code=403)
        return await call_next(request)

    def _spawn_build() -> int:
        if spawn is not None:
            return spawn(root)
        proc = subprocess.Popen(  # noqa: S603 — fixed argv
            [sys.executable, "-m", "autoproduct.cli", "create", str(root),
             "--profile", _profile(root), "--yes"],
            cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        (root / ".mas").mkdir(exist_ok=True)
        (root / ".mas" / "build.pid").write_text(str(proc.pid), encoding="utf-8")
        return proc.pid

    def _profile(workspace: Path) -> str:
        data = yaml.safe_load(
            (workspace / ".mas" / "project.yaml").read_text(encoding="utf-8")
        )
        return data["profile"]

    @app.get("/", response_class=HTMLResponse)
    def home():
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
            return _page(
                _("title_building"),
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
                "      +(ICONS[t.state]?'':' ('+t.state+')');\n"
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
            return _page(
                _("title_interrupted"),
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
                return _page(
                    _("title_confirm_feature"),
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
            return _page(
                _("title_product"),
                f"<pre>{_md(report)}</pre>{acceptance}{gallery}{retry_block}"
                f"<h2>{_('h_features')}</h2>"
                f"{feature_cards or no_features}"
                f"<h2>{_('h_something_wrong')}</h2>"
                f"<p class=muted>{_('correction_hint')}</p>"
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
            return _page(
                _("title_confirm_plan"),
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
        from autoproduct.upstream.fdr import template_for

        current = (
            fdr.read_text(encoding="utf-8") if fdr.exists() else template_for(lang)
        )
        return _page(
            _("title_describe"),
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
        form = await request.form()
        (root / "FDR.md").write_text(str(form.get("fdr", "")), encoding="utf-8")
        for stale in ("FDR-QUESTIONS.md",):
            (root / stale).unlink(missing_ok=True)
        from starlette.concurrency import run_in_threadpool

        from autoproduct.upstream.autopilot import run_autopilot

        # LLM calls block for minutes — off the event loop (sweep finding),
        # or the progress page can't even poll while the assessor runs.
        await run_in_threadpool(
            run_autopilot, root, root / "FDR.md", yes=False, provider=provider
        )
        return RedirectResponse("/", status_code=303)

    @app.get("/acceptance", response_class=HTMLResponse)
    def acceptance():
        return _page(
            _("title_acceptance"),
            f"<pre>{_md(root / 'product' / 'ACCEPTANCE.md')}</pre>"
            f"<p><a href='/'>{_('link_back')}</a></p>",
        )

    @app.get("/shots/{name}")
    def shot(name: str):
        from fastapi.responses import FileResponse

        path = (root / "product" / "screenshots" / name).resolve()
        if not path.is_file() or path.parent != (root / "product" / "screenshots").resolve():
            raise HTTPException(404)
        return FileResponse(path)

    @app.post("/correct")
    async def correct(request: Request):
        form = await request.form()
        complaint = str(form.get("complaint", "")).strip()
        if complaint:
            from starlette.concurrency import run_in_threadpool

            from autoproduct.upstream.correction import run_correction

            result = await run_in_threadpool(
                run_correction, root, complaint, provider=provider
            )
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
                [sys.executable, "-m", "autoproduct.cli", "retry-task", task_id,
                 "--repo-dir", str(root)],
                cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            (root / ".mas" / "build.pid").write_text(str(proc.pid), encoding="utf-8")
        return RedirectResponse("/", status_code=303)

    @app.post("/undo")
    def undo():
        from autoproduct.upstream.autopilot import undo_last

        undo_last(root)
        return RedirectResponse("/", status_code=303)

    @app.post("/feature")
    async def feature(request: Request):
        form = await request.form()
        fdr_text = str(form.get("fdr", "")).strip()
        if fdr_text:
            fdr_path = root / ".mas" / "pending-feature.md"
            fdr_path.write_text(fdr_text, encoding="utf-8")
            from starlette.concurrency import run_in_threadpool

            from autoproduct.upstream.autopilot import run_feature

            await run_in_threadpool(
                run_feature, root, fdr_path, provider=provider, yes=False
            )
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
                proc = subprocess.Popen(  # noqa: S603
                    [sys.executable, "-m", "autoproduct.cli", "add", str(fdr_path),
                     "--repo-dir", str(root), "--yes"],
                    cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                (root / ".mas" / "build.pid").write_text(str(proc.pid), encoding="utf-8")
        return RedirectResponse("/", status_code=303)

    @app.post("/build")
    def build():
        if not _build_running(root):
            _spawn_build()
        return RedirectResponse("/", status_code=303)

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
                 lang: str = DEFAULT_LANGUAGE) -> None:
    import uvicorn

    uvicorn.run(create_studio_app(repo_dir, provider=provider, lang=lang),
                host=host, port=port, log_level="warning")
