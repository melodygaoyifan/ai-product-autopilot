"""The production loop, founder-facing (Take it live · It's broken · Housekeeping).

The build flow ends with "your product works in this folder"; these
surfaces carry the founder the rest of the way in their own language:
how to run it somewhere real, whether it is answering right now, what to
do when it breaks (the existing triage MAS, reached from a textarea
instead of an incident YAML), and what upkeep the sweep role has queued.

Same veneer rule as every Studio panel: everything here reads and writes
the workspace files the CLI owns (.mas/live.yaml, .mas/incidents/,
.mas/sweep/) — the Studio is never a second source of truth. And the
same honesty rule: avs never deploys on its own; the boundary is stated
on the page, not hidden in a doc.
"""

from __future__ import annotations

import datetime as dt
import html
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import yaml

LIVE_FILE = "live.yaml"


# --- verify-it's-live probe ---------------------------------------------------


def probe_live(root: Path, url: str) -> dict:
    """One GET against the founder's own deployed URL; the result is
    written to .mas/live.yaml so the page remembers the last check."""
    url = url.strip()
    result: dict = {"url": url, "checked_at": dt.datetime.now().isoformat(timespec="seconds")}
    if not url.startswith(("http://", "https://")):
        result.update(ok=False, detail="only http:// and https:// URLs")
    else:
        started = time.monotonic()
        try:
            with urllib.request.urlopen(url, timeout=8) as response:  # noqa: S310 — scheme checked above
                elapsed = time.monotonic() - started
                result.update(
                    ok=200 <= response.status < 400,
                    status=response.status,
                    detail=f"answered {response.status} in {elapsed:.1f}s",
                )
        except urllib.error.HTTPError as exc:
            result.update(ok=False, status=exc.code,
                          detail=f"answered {exc.code} ({exc.reason})")
        except Exception as exc:  # noqa: BLE001 — every network failure is a plain sentence
            result.update(ok=False, detail=f"no answer: {exc}")
    mas = root / ".mas"
    mas.mkdir(exist_ok=True)
    (mas / LIVE_FILE).write_text(
        yaml.safe_dump(result, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return result


def last_probe(root: Path) -> dict | None:
    path = root / ".mas" / LIVE_FILE
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or None
    except yaml.YAMLError:
        return None


# --- the Take-it-live page body ----------------------------------------------


def live_body(root: Path, t_: Callable[[str], str], profile: str) -> str:
    from ai_venture_studio.upstream.provisioning import CLOUD_CATALOG, preview_env

    has_catalog = profile in CLOUD_CATALOG
    guide_form = (
        f"<form method=post action=/live/guide>"
        f"<button class=secondary>{t_('btn_cloud_guide')}</button></form>"
        f"<p class=muted>{t_('live_guide_effect')}</p>"
        if has_catalog
        # A button that silently does nothing is worse than no button: the
        # data/game profiles have no guided cloud catalog, and saying so is
        # the honest rendering.
        else f"<p class=muted>{t_('live_no_catalog')}</p>"
    )

    # 1 · run it: the boot contract, verbatim — the same command every
    # verification harness used, so it is known to work.
    entry = next(
        (e for e in ("app/main.py", "main.py", "app.py") if (root / e).exists()),
        "app/main.py",
    )
    env = preview_env(root)
    env_line = " ".join(f"{k}=…" for k in sorted(env)) if env else ""
    run_card = (
        f"<div class=card><b>{t_('live_run')}</b>"
        f"<p>{t_('live_run_hint')}</p>"
        f"<pre>{html.escape(f'PORT=8000 {env_line} python {entry}'.replace('  ', ' '))}</pre>"
        f"<p class=muted>{t_('live_run_note')}</p></div>"
    )

    # 2 · persistence: what is provisioned, or the guided cloud steps.
    services = {}
    services_path = root / ".mas" / "services.yaml"
    if services_path.exists():
        try:
            services = yaml.safe_load(services_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            services = {}
    guide = root / "SERVICES.md"
    if guide.exists():
        rewrite_form = (
            f"<form method=post action=/live/guide>"
            f"<button class=secondary>{t_('btn_cloud_guide_again')}</button></form>"
            if has_catalog else ""
        )
        persistence_inner = (
            f"<details open><summary>{t_('live_cloud_steps')}</summary>"
            f"<pre>{html.escape(guide.read_text(encoding='utf-8'))}</pre></details>"
            f"{rewrite_form}"
        )
    elif services:
        names = ", ".join(sorted(services))
        persistence_inner = (
            f"<p class=ok>{t_('live_local_db')} <code>{html.escape(names)}</code></p>"
            f"{guide_form}"
        )
    else:
        persistence_inner = (
            f"<p class=muted>{t_('live_no_services')}</p>"
            f"{guide_form}"
        )
    persistence_card = (
        f"<div class=card><b>{t_('live_persistence')}</b>{persistence_inner}</div>"
    )

    # 3 · the boundary, stated where the button would be.
    boundary_card = (
        f"<div class=card><b>{t_('live_boundary')}</b>"
        f"<p class=muted>{t_('live_boundary_note')}</p></div>"
    )

    # 4 · verify: is it answering right now?
    last = last_probe(root)
    if last:
        css = "ok" if last.get("ok") else "bad"
        last_line = (
            f"<p class={css}>{html.escape(str(last.get('url', '')))} — "
            f"{html.escape(str(last.get('detail', '')))} "
            f"<span class=muted>({html.escape(str(last.get('checked_at', '')))})"
            f"</span></p>"
        )
    else:
        last_line = f"<p class=muted>{t_('live_never_checked')}</p>"
    verify_card = (
        f"<div class=card><b>{t_('live_verify')}</b>{last_line}"
        f"<form method=post action=/live/probe>"
        f"<input name=url style='width:70%' placeholder='https://…' required> "
        f"<button>{t_('btn_check_live')}</button></form></div>"
    )

    # 5 · the incident front door lives here too: an adopted brownfield
    # repo has no product report page, and "it broke in production" is a
    # take-it-live concern. Same route, same triage MAS; when maintenance
    # is below its substrate floor the refusal renders in this page's own
    # words (the ladder reason), never a 500.
    broken_card = (
        f"<div class=card><b>{t_('h_broken')}</b>"
        f"<p class=muted>{t_('inc_hint')}</p>"
        f"<form method=post action=/incident>"
        f"<textarea name=description style='min-height:80px' "
        f"placeholder='{t_('inc_placeholder')}'></textarea>"
        f"<p><button>{t_('btn_incident')}</button></p></form></div>"
    )

    return (
        run_card + persistence_card + boundary_card + verify_card
        + broken_card + housekeeping_card(root, t_)
    )


def run_housekeeping(root: Path):
    """One sweep pass from the page — identical to `avs sweep` (harvest the
    queues the ledgers already keep, then the rung-gated pass). With no
    sweep.yaml this is SW0: report-only, nothing changed, clean passes
    recorded. Raises SweepConfigError on an invalid config — the route
    renders it, never swallows it."""
    from ai_venture_studio.lanes.delivery import flag_lint
    from ai_venture_studio.sweep import (
        harvest_queues,
        load_sweep_config,
        run_sweep_pass,
    )

    day = dt.date.today()
    config = load_sweep_config(root / ".mas")
    flags_file = root / ".mas" / "flags.yaml"
    flag_issues = (
        flag_lint(flags_file.read_text(encoding="utf-8"), {}, today=day)
        if flags_file.exists() else []
    )
    contributing = root / "CONTRIBUTING.md"
    chores = harvest_queues(
        root, today=day, flag_issues=flag_issues,
        contributing_text=(
            contributing.read_text(encoding="utf-8")
            if contributing.exists() else ""
        ),
    )
    return run_sweep_pass(root, chores, config=config, at=day.isoformat())


def housekeeping_card(root: Path, t_: Callable[[str], str]) -> str:
    """The sweep role's latest digest, in the owner's language. Grey when
    sweep has never run — absence is stated, never rendered as tidy."""
    sweep_dir = root / ".mas" / "sweep"
    digests = sorted(sweep_dir.glob("digest-*.yaml")) if sweep_dir.is_dir() else []
    head = f"<b>{t_('house_head')}</b>"
    run_form = (
        f"<form method=post action=/live/sweep>"
        f"<button class=secondary>{t_('btn_run_sweep')}</button></form>"
        f"<p class=muted>{t_('house_run_note')}</p>"
    )
    if not digests:
        return (
            f"<div class=card>{head}"
            f"<p class=muted>{t_('house_never')} <code>avs sweep</code></p>"
            f"{run_form}</div>"
        )
    try:
        digest = yaml.safe_load(digests[-1].read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return f"<div class=card>{head}<p class=bad>{t_('house_unreadable')}</p></div>"
    if digest.get("clean_pass"):
        body = f"<p class=ok>{t_('house_clean')}</p>"
    else:
        chores = digest.get("chores") or []
        rows = "".join(
            f"<li>{html.escape(str(c.get('item', '')))} — "
            f"<span class=muted>{html.escape(str(c.get('detail', ''))[:120])}</span></li>"
            for c in chores[:5]
        )
        more = len(chores) - 5
        body = (
            f"<p>{len(chores)} {t_('house_items')} · "
            f"{len(digest.get('actionable') or [])} {t_('house_actionable')}</p>"
            f"<ul>{rows}</ul>"
            + (f"<p class=muted>+{more}</p>" if more > 0 else "")
        )
    return (
        f"<div class=card>{head}{body}"
        f"<p class=muted>{t_('house_note')} "
        f"<span class=muted>({html.escape(str(digest.get('at', '')))})</span></p>"
        f"{run_form}</div>"
    )


# --- It's broken: plain-English intake to the triage MAS ----------------------


def incident_intake(root: Path, description: str, provider: str):
    """A founder sentence becomes a real incident: same Incident model,
    same triage/root-cause MAS, same artifacts — only the front door is
    a textarea. The result is persisted so the fix step can reload it."""
    from ai_venture_studio.maintenance import Incident, run_maintenance

    description = description.strip()
    title = description.splitlines()[0][:100] if description else "incident"
    incident = Incident(
        id=f"inc-{int(time.time())}", title=title, body=description,
        source="founder",
    )
    result = run_maintenance(incident, repo_dir=str(root), provider=provider)
    record = {
        "incident": incident.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
    }
    out = root / ".mas" / "incidents" / incident.id
    out.mkdir(parents=True, exist_ok=True)
    (out / "founder.yaml").write_text(
        yaml.safe_dump(record, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return incident, result


def incident_body(t_: Callable[[str], str], incident_id: str, result) -> str:
    verdict = str(result.verdict.value)
    css = {"TRIAGED_LOW_PRIORITY": "ok", "ROOT_CAUSE_PROPOSED": "warn"}.get(
        verdict, "bad"
    )
    # The founder's sentence first; the machine verdict stays visible but
    # demoted — ESCALATE_INCIDENT_UNRESOLVED is not a sentence anyone
    # non-technical should have to parse.
    plain = {
        "TRIAGED_LOW_PRIORITY": t_("inc_v_low"),
        "ROOT_CAUSE_PROPOSED": t_("inc_v_cause"),
    }.get(verdict, t_("inc_v_escalate"))
    summary = result.summary
    if summary.startswith(verdict):
        summary = summary[len(verdict):].lstrip(" —-·")
    lines = (
        f"<p class={css}><b>{plain}</b></p>"
        f"<p class=muted><code>{html.escape(verdict)}</code> — "
        f"{html.escape(summary)}</p>"
    )
    # Hypothesis and next-step lines only when a cause was actually
    # proposed. On the escalate path the model's fields are non-answers
    # ("insufficient evidence", "propose fix-PR") that contradict the
    # verdict one line above them; the founder-useful information there is
    # WHERE the technical record lives, to hand to whoever maintains it.
    if verdict == "ROOT_CAUSE_PROPOSED" and result.root_cause:
        lines += (
            f"<p>{t_('inc_hypothesis')}: "
            f"{html.escape(result.root_cause.hypothesis)} "
            f"<span class=muted>({result.root_cause.confidence}%)</span></p>"
            f"<p class=muted>{t_('inc_next')}: "
            f"{html.escape(result.root_cause.next_action)}</p>"
        )
    elif verdict not in ("ROOT_CAUSE_PROPOSED", "TRIAGED_LOW_PRIORITY"):
        lines += (
            f"<p>{t_('inc_saved_at')} "
            f"<code>.mas/incidents/{html.escape(incident_id)}/</code></p>"
        )
    fix_form = ""
    if verdict == "ROOT_CAUSE_PROPOSED":
        fix_form = (
            f"<form method=post action=/incident/fix>"
            f"<input type=hidden name=incident_id value='{html.escape(incident_id)}'>"
            f"<button>{t_('btn_try_fix')}</button></form>"
            f"<p class=muted>{t_('inc_fix_note')}</p>"
        )
    return (
        f"<div class=card><b>{t_('inc_head')}</b>{lines}{fix_form}</div>"
        f"<p><a href='/'>{t_('link_back')}</a></p>"
    )


def attempt_incident_fix(root: Path, incident_id: str, provider: str):
    """The --fix path, from the page: the click IS the human approval,
    and the fix re-enters code review like any other change (same
    contract as `avs triage --fix`)."""
    from ai_venture_studio.maintenance import Incident
    from ai_venture_studio.maintenance.fixpr import generate_fix_pr
    from ai_venture_studio.maintenance.review import RootCauseResult

    record_path = root / ".mas" / "incidents" / incident_id / "founder.yaml"
    record = yaml.safe_load(record_path.read_text(encoding="utf-8")) or {}
    incident = Incident.model_validate(record["incident"])
    root_cause = RootCauseResult.model_validate(
        (record.get("result") or {}).get("root_cause") or {}
    )
    return generate_fix_pr(
        incident, root_cause, repo_dir=str(root), provider=provider
    )


def fix_body(t_: Callable[[str], str], attempt) -> str:
    css = "ok" if attempt.status == "opened" else (
        "warn" if attempt.status in ("branch_only", "abstained") else "bad"
    )
    parts = f"<p class={css}><b>{html.escape(attempt.status)}</b>"
    if attempt.branch:
        parts += f" · {t_('fix_branch')} <code>{html.escape(attempt.branch)}</code>"
    if attempt.pr_url:
        parts += (
            f" · <a href='{html.escape(attempt.pr_url)}'>"
            f"{html.escape(attempt.pr_url)}</a>"
        )
    parts += "</p>"
    if attempt.detail:
        parts += f"<p class=muted>{html.escape(attempt.detail)}</p>"
    if attempt.files_changed:
        parts += (
            f"<p class=muted>{t_('fix_files')}: "
            f"{html.escape(', '.join(attempt.files_changed))}</p>"
        )
    return (
        f"<div class=card><b>{t_('fix_head')}</b>{parts}"
        f"<p class=muted>{t_('inc_fix_note')}</p></div>"
        f"<p><a href='/'>{t_('link_back')}</a></p>"
    )
