"""Studio modes — the three doors (doc 24) reach the UI.

The editions system (ADR-U26/U27) already encodes who is at the keyboard —
solo founder, engineer, enterprise team — but the Studio rendered the same
page for all three. A mode is the UI-side reading of that choice:

- ``founder``    — the original flow, unchanged, and the default.
- ``engineer``   — adds a build-internals card: task IDs as the CLI takes
  them, verbatim states, and the command equivalent of every button.
- ``enterprise`` — adds a governance card: the resolved edition's substrate
  rung, WIP limit, gate-owner rule, never-batched gates, and the
  attestation-ledger count.

Same rule as editions themselves: a mode may only ADD visibility, never
remove a page, a form, or a required action — the UI analogue of
narrowing-never-widening (invariant 14.21). Every panel is read from the
same workspace files the CLI writes; the Studio stays a veneer, never a
second source of truth.

Resolution: an explicit ``--mode`` wins; otherwise the workspace's
``.mas/edition.yaml`` (solo→founder, engineer→engineer,
enterprise→enterprise); otherwise founder. An unknown explicit mode is a
loud startup error — same policy as a missing i18n key, because a Studio
serving the wrong audience quietly is worse than one that refuses to start.

Since v0.56 the mode is adaptable per request, never adaptive: a visible
switcher on every page (`mode_strip`) sets ``?mode=`` and a cookie; the
resolution above only supplies the default. The system never flips the
mode behind the user's back — auto-adapting UIs lose the user's trust in
where things are (Findlater & McGrenere, CHI 2004), and a mode that isn't
loudly visible invites mode errors.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Callable

import yaml

MODES = ("founder", "engineer", "enterprise")
# solo maps to founder rather than sharing a name: the edition is a pipeline
# preset (WIP 1, weekly review), the mode is a reading depth — a solo founder
# wants the plain flow, which is exactly the founder page.
EDITION_TO_MODE = {"solo": "founder", "engineer": "engineer",
                   "enterprise": "enterprise"}


class StudioModeError(ValueError):
    """An explicit mode the Studio does not have. Startup refuses."""


def mode_strip(current: str, t_: Callable[[str], str]) -> str:
    """The always-visible mode switcher. Two redundant cues for the active
    mode (bold + no link) so the current state is never ambiguous, and the
    other modes stay discoverable from every page."""
    parts = []
    for mode in MODES:
        label = t_(f"mode_{mode}")
        if mode == current:
            parts.append(f"<b>{label}</b>")
        else:
            parts.append(f"<a href='/?mode={mode}'>{label}</a>")
    return (
        f"<p class=muted>{t_('mode_strip_label')} " + " · ".join(parts) + "</p>"
    )


def resolve_mode(root: Path, explicit: str | None = None) -> str:
    if explicit:
        mode = str(explicit).strip().lower()
        if mode not in MODES:
            raise StudioModeError(
                f"unknown studio mode {explicit!r}; modes: {', '.join(MODES)}"
            )
        return mode
    path = root / ".mas" / "edition.yaml"
    if path.exists():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            # A hand-corrupted edition file must not take the Studio down;
            # founder mode still serves, and the enterprise panel is where
            # edition problems are surfaced loudly when asked for.
            return "founder"
        return EDITION_TO_MODE.get(str(raw.get("edition")), "founder")
    return "founder"


def recent_reviews(root: Path, limit: int = 10) -> list[dict]:
    """Bounded, newest-first review listing — the server.py `/reviews`
    pattern; an unbounded scan per page load is the bug it avoids."""
    reviews_dir = root / ".mas" / "reviews"
    if not reviews_dir.is_dir():
        return []
    rows = []
    newest_first = sorted(
        (d for d in reviews_dir.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )[: max(1, min(limit, 50))]
    for review_dir in newest_first:
        final = sorted(review_dir.glob("[0-9]*-final.yaml"))
        verdict = None
        if final:
            try:
                data = yaml.safe_load(final[-1].read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                data = {}
            verdict = data.get("verdict")
        rows.append({"review_id": review_dir.name, "verdict": verdict})
    return rows


def voter_health(root: Path) -> list[dict]:
    """Per-voter invocation counts from `.mas/voters/*/log.yaml` — the same
    raw material the compounding loop reads, summarized instead of hidden
    inside a weekly proposal."""
    voters_dir = root / ".mas" / "voters"
    if not voters_dir.is_dir():
        return []
    rows = []
    for voter_dir in sorted(d for d in voters_dir.iterdir() if d.is_dir()):
        log_path = voter_dir / "log.yaml"
        if not log_path.exists():
            continue
        try:
            entries = yaml.safe_load(log_path.read_text(encoding="utf-8")) or []
        except yaml.YAMLError:
            continue
        blocked = sum(
            1 for e in entries if str(e.get("status", "")).startswith("BLOCKED")
        )
        substituted = sum(1 for e in entries if e.get("substituted_from"))
        rows.append({
            "voter": voter_dir.name, "total": len(entries),
            "blocked": blocked, "substituted": substituted,
        })
    return rows


def review_timeline_body(root: Path, review_id: str,
                         t_: Callable[[str], str]) -> str:
    """One review's mirror as a step table — `avs replay` in the browser,
    reading the same NN-<node>.yaml files."""
    from ai_venture_studio.replay import load_replay, summarize_step

    replay = load_replay(root / ".mas" / "reviews", review_id)
    rows = "".join(
        f"<tr><td>{step.step}</td><td><code>{html.escape(step.node)}</code></td>"
        f"<td>{html.escape(summarize_step(step))}</td></tr>"
        for step in replay.steps
    )
    verdict = replay.verdict or "—"
    duration = f"{replay.duration_s:.1f}s" if replay.duration_s else "—"
    return (
        f"<p>{t_('review_verdict')}: <b>{html.escape(str(verdict))}</b> · "
        f"{t_('review_duration')}: {html.escape(duration)}</p>"
        f"<table>{rows}</table>"
        f"<form method=post action='/review/{html.escape(review_id)}/evidence'>"
        f"<button class=secondary>{t_('btn_evidence')}</button></form>"
        f"<p class=muted>{t_('evidence_note')}</p>"
        f"<p><a href='/'>{t_('link_back')}</a></p>"
    )


def engineer_panel(root: Path, t_: Callable[[str], str],
                   tasks: list[dict]) -> str:
    profile = ""
    project = root / ".mas" / "project.yaml"
    if project.exists():
        try:
            data = yaml.safe_load(project.read_text(encoding="utf-8")) or {}
            profile = str(data.get("profile", ""))
        except yaml.YAMLError:
            profile = ""
    if tasks:
        rows = "".join(
            f"<tr><td><code>{html.escape(task['id'])}</code></td>"
            f"<td>{html.escape(task['state'])}</td>"
            f"<td>{html.escape(task['title'])}</td></tr>"
            for task in tasks
        )
        table = f"<table>{rows}</table>"
    else:
        table = f"<p class=muted>{t_('eng_no_plan')}</p>"
    profile_line = (
        f"<p class=muted>{t_('eng_profile')}: <code>{html.escape(profile)}"
        "</code></p>"
        if profile else ""
    )
    hints = (
        f"<details><summary class=muted>{t_('eng_cli')}</summary>"
        f"<pre>{html.escape(t_('eng_cli_body'))}</pre></details>"
    )
    reviews = recent_reviews(root)
    if reviews:
        review_rows = "".join(
            f"<tr><td><a href='/review/{html.escape(r['review_id'])}'>"
            f"<code>{html.escape(r['review_id'])}</code></a></td>"
            f"<td>{html.escape(str(r['verdict'] or '…'))}</td></tr>"
            for r in reviews
        )
        reviews_block = (
            f"<p><b>{t_('eng_reviews')}</b></p><table>{review_rows}</table>"
        )
    else:
        reviews_block = (
            f"<p><b>{t_('eng_reviews')}</b> "
            f"<span class=muted>{t_('eng_reviews_none')}</span></p>"
        )
    voters = voter_health(root)
    if voters:
        voter_rows = "".join(
            f"<tr><td><code>{html.escape(v['voter'])}</code></td>"
            f"<td>{v['total']}</td><td>{v['blocked']}</td>"
            f"<td>{v['substituted']}</td></tr>"
            for v in voters
        )
        voters_block = (
            f"<p><b>{t_('eng_voter_health')}</b> "
            f"<span class=muted>{t_('eng_voter_cols')}</span></p>"
            f"<table>{voter_rows}</table>"
        )
    else:
        voters_block = ""
    return (
        f"<div class=card><b>{t_('h_engineer')}</b>"
        f"<p class=muted>{t_('mode_note_engineer')}</p>"
        f"{profile_line}{table}{reviews_block}{voters_block}{hints}</div>"
    )


def enterprise_panel(root: Path, t_: Callable[[str], str]) -> str:
    """The governance spokes render independently: a workspace without an
    edition file still has a stage ladder, a dwell distribution, and an
    automation arming state worth seeing.

    Order follows the enterprise-dashboard convention (posture verdict →
    trust/procurement facts → what-we-found → drill-down): the one-line
    answer first, the security reviewer's questions second, the evidence
    below."""
    return (
        _posture_html(root, t_)
        + _trust_html(root, t_)
        + _codebase_html(root, t_)
        + _edition_card(root, t_)
        + _stage_grid_html(root, t_)
        + _deploy_reviews_html(root, t_)
        + _dwell_html(root, t_)
        + _automation_html(root, t_)
    )


def _deploy_reviews_html(root: Path, t_: Callable[[str], str]) -> str:
    """Gate 5 history where the gate owner already is: the last deploy
    recommendations, newest first, from the same mirrors `avs
    deploy-review` writes. Grey with the command when none have run —
    absence of deploy review must never read as reviewed-and-fine."""
    head = f"<b>{t_('gov_deploys')}</b>"
    base = root / ".mas" / "deploy-reviews"
    runs = sorted(
        (d for d in base.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime, reverse=True,
    )[:5] if base.is_dir() else []
    if not runs:
        return (
            f"<div class=card>{head}"
            f"<p class=muted>{t_('gov_no_deploys')} "
            f"<code>avs deploy-review main...HEAD</code></p></div>"
        )
    rows = ""
    for run_dir in runs:
        final = sorted(run_dir.glob("[0-9]*-final.yaml"))
        verdict, branch = "…", ""
        if final:
            try:
                data = yaml.safe_load(final[-1].read_text(encoding="utf-8")) or {}
                verdict = str(data.get("verdict", "…"))
                branch = str(data.get("branch", ""))
            except yaml.YAMLError:
                verdict = "?"
        rows += (
            f"<tr><td><code>{html.escape(run_dir.name)}</code></td>"
            f"<td>{html.escape(verdict)}</td>"
            f"<td class=muted>{html.escape(branch)}</td></tr>"
        )
    return (
        f"<div class=card>{head}<table>{rows}</table>"
        f"<p class=muted>{t_('gov_deploys_note')}</p></div>"
    )


def governance_posture(root: Path) -> dict[str, list[str]]:
    """Machine-readable spoke states: measured / unconfigured / attention.

    'Unconfigured' is its own state on purpose — a grey answer. A dashboard
    that renders green over an unmeasured workspace teaches its readers to
    ignore green (the GitHub-security-overview lesson: 'not enabled' is
    never 'healthy')."""
    from ai_venture_studio.adoption.attestation import verify_ledger
    from ai_venture_studio.adoption.dwell import gate_dwell_report
    from ai_venture_studio.adoption.substrate import load_substrate_profile
    from ai_venture_studio.automation import (
        AUTOMERGE_POLICY,
        DEPLOY_EXEC_POLICY,
        PolicyError,
        load_policy,
    )
    from ai_venture_studio.editions import EditionError, load_workspace_edition

    posture: dict[str, list[str]] = {
        "measured": [], "unconfigured": [], "attention": [],
    }

    try:
        edition = load_workspace_edition(root)
        if edition is None:
            posture["unconfigured"].append("edition")
        else:
            posture["measured"].append("edition")
    except EditionError:
        posture["attention"].append("edition")

    try:
        substrate = load_substrate_profile(root)
    except ValueError:
        posture["attention"].append("substrate")
    else:
        posture[
            "unconfigured" if substrate is None else "measured"
        ].append("substrate")

    dwell = gate_dwell_report(root)
    if dwell.median_s is None:
        posture["unconfigured"].append("gate dwell")
    elif dwell.rubber_stamp:
        posture["attention"].append("gate dwell")
    else:
        posture["measured"].append("gate dwell")

    if not (root / ".mas" / "attestation" / "ledger.jsonl").exists():
        posture["unconfigured"].append("attestation")
    else:
        try:
            posture[
                "measured" if verify_ledger(root).ok else "attention"
            ].append("attestation")
        except ValueError:
            posture["attention"].append("attestation")

    # Policies always have a knowable state (absent file = disarmed default),
    # so they count as measured unless the file itself is invalid.
    policy_state = "measured"
    for filename in (AUTOMERGE_POLICY, DEPLOY_EXEC_POLICY):
        try:
            load_policy(root, filename)
        except PolicyError:
            policy_state = "attention"
    posture[policy_state].append("automation policies")
    return posture


def _posture_html(root: Path, t_: Callable[[str], str]) -> str:
    posture = governance_posture(root)
    parts = []
    if posture["attention"]:
        parts.append(
            f"<span class=bad>{t_('gov_posture_attention')} "
            f"{html.escape(', '.join(posture['attention']))}</span>"
        )
    if posture["measured"]:
        parts.append(
            f"<span class=ok>{t_('gov_posture_measured')} "
            f"{html.escape(', '.join(posture['measured']))}</span>"
        )
    if posture["unconfigured"]:
        parts.append(
            f"<span class=muted>{t_('gov_posture_unmeasured')} "
            f"{html.escape(', '.join(posture['unconfigured']))}</span>"
        )
    line = " · ".join(parts)
    return (
        f"<div class=card><b>{t_('gov_posture')}</b>"
        f"<p>{line}</p>"
        f"<p class=muted>{t_('gov_posture_note')}</p></div>"
    )


def _trust_html(root: Path, t_: Callable[[str], str]) -> str:
    """The procurement answers, on screen: which model door, authenticated
    how (presence only — never a value), which forge, what leaves the
    machine, and what this workspace has spent. A security reviewer should
    read this without a meeting."""
    import os

    from ai_venture_studio import spend as spend_mod
    from ai_venture_studio.forge import _remote_forge

    mode = (os.environ.get("AVS_ANTHROPIC_MODE", "").strip().lower()
            or "direct")
    if os.environ.get("ANTHROPIC_API_KEY"):
        auth = t_("trust_auth_env")
    elif os.environ.get("ANTHROPIC_API_KEY_FILE") or os.environ.get(
        "ANTHROPIC_AUTH_TOKEN_FILE"
    ):
        auth = t_("trust_auth_file")
    elif os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        auth = t_("trust_auth_gateway")
    else:
        auth = t_("trust_auth_none")
    auth_css = "muted" if auth == t_("trust_auth_none") else "ok"

    forge = _remote_forge(str(root))
    forge_cell = (
        f"<code>{html.escape(forge)}</code>" if forge
        else f"<span class=muted>{t_('trust_forge_none')}</span>"
    )

    try:
        summary = spend_mod.summarize(spend_mod.read_entries(root))
    except Exception:  # noqa: BLE001 — a corrupt ledger must not kill the page
        summary = None
    if summary is None or summary.calls == 0:
        spend_cell = f"<span class=muted>{t_('trust_spend_none')}</span>"
    else:
        floor = f"{t_('trust_spend_floor')} " if summary.is_floor else ""
        spend_cell = (
            f"{floor}${summary.usd:.2f} · {summary.calls} calls · "
            f"{summary.total_tokens:,} tokens"
        )

    rows = (
        f"<tr><td>{t_('trust_provider')}</td>"
        f"<td><code>{html.escape(mode)}</code> · "
        f"<span class={auth_css}>{auth}</span></td></tr>"
        f"<tr><td>{t_('trust_forge')}</td><td>{forge_cell}</td></tr>"
        f"<tr><td>{t_('trust_egress')}</td>"
        f"<td class=muted>{t_('trust_egress_note')}</td></tr>"
        f"<tr><td>{t_('trust_spend')}</td><td>{spend_cell}</td></tr>"
    )
    return (
        f"<div class=card><b>{t_('trust_head')}</b>"
        f"<p class=muted>{t_('trust_note')}</p><table>{rows}</table></div>"
    )


def _codebase_html(root: Path, t_: Callable[[str], str]) -> str:
    """The brownfield what-we-found report (the Renovate-onboarding lesson:
    prove comprehension before asking for configuration). Reads the map
    `avs map` / `init --adopt` wrote; absent map is a grey state with the
    one command that fills it."""
    path = root / ".mas" / "codebase-map.yaml"
    head = f"<b>{t_('code_head')}</b>"
    if not path.exists():
        return (
            f"<div class=card>{head}"
            f"<p class=muted>{t_('code_none')} "
            f"<code>avs map .</code></p>"
            f"<p class=muted>{t_('gov_action_reload')}</p></div>"
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return (
            f"<div class=card>{head}"
            f"<p class=bad>{t_('code_unreadable')}</p></div>"
        )
    langs = ", ".join(
        f"{lang} ({count})" for lang, count in (data.get("languages") or {}).items()
    )
    modules = sorted(
        data.get("modules") or [],
        key=lambda m: m.get("lines", 0), reverse=True,
    )
    entries = ", ".join(data.get("entry_points") or []) or "—"
    routes = len(data.get("routes") or [])
    top = "".join(
        f"<tr><td><code>{html.escape(str(m.get('name', '')))}</code></td>"
        f"<td>{m.get('files', 0)} files · {m.get('lines', 0):,} lines</td></tr>"
        for m in modules[:6]
    )
    more = (
        f"<p class=muted>+{len(modules) - 6} more modules</p>"
        if len(modules) > 6 else ""
    )
    return (
        f"<div class=card>{head}"
        f"<p>{html.escape(langs)} · {data.get('total_files', 0)} files · "
        f"{data.get('total_lines', 0):,} lines · "
        f"{t_('code_http')}: {routes}</p>"
        f"<p class=muted>{t_('code_entries')}: <code>{html.escape(entries)}"
        f"</code></p><table>{top}</table>{more}"
        f"<p class=muted>{t_('code_note')}</p></div>"
    )


def _edition_card(root: Path, t_: Callable[[str], str]) -> str:
    from ai_venture_studio.editions import EditionError, load_workspace_edition

    head = (
        f"<b>{t_('h_governance')}</b>"
        f"<p class=muted>{t_('mode_note_enterprise')}</p>"
    )
    try:
        edition = load_workspace_edition(root)
    except EditionError as exc:
        return (
            f"<div class=card>{head}<p class=bad>{t_('gov_edition_error')}: "
            f"{html.escape(str(exc))}</p></div>"
        )
    if edition is None:
        # Grey state, not a dead end: the exact command, what it changes,
        # and the feedback loop (this page re-reads the file every load).
        return (
            f"<div class=card>{head}<p class=warn>{t_('gov_no_edition')}</p>"
            f"<p><code>avs init . --profile enterprise-web --edition "
            f"enterprise --gate-owner \"&lt;name&gt;\"</code></p>"
            f"<p class=muted>{t_('gov_edition_effect')} "
            f"{t_('gov_action_reload')}</p></div>"
        )

    defaults = edition.defaults or {}
    policy = edition.gate_policy or {}
    never = ", ".join(sorted(str(g) for g in policy.get("never_consolidate", [])))
    rows = "".join(
        f"<tr><td>{label}</td><td>{value}</td></tr>"
        for label, value in (
            (t_("gov_edition"), f"<code>{html.escape(edition.edition)}</code>"),
            (t_("gov_rung"),
             html.escape(str(defaults.get("substrate_rung", "S0")))),
            (t_("gov_wip"), html.escape(str(defaults.get("wip_limit", "")))),
            (t_("gov_weekly"),
             html.escape(str((edition.attention or {}).get(
                 "weekly_review_minutes", "")))),
            (t_("gov_never"), html.escape(never)),
        )
    )
    owner = (
        t_("gov_gate_owner_yes") if policy.get("require_gate_owner")
        else t_("gov_gate_owner_no")
    )
    if policy.get("gate_owner"):
        # The named human, not just the rule — who is accountable is the
        # first thing a CAB asks.
        owner += f" <b>{html.escape(str(policy['gate_owner']))}</b>"
    return (
        f"<div class=card>{head}<table>{rows}</table>"
        f"<p>{owner}</p><p>{_attestation_html(root, t_)}</p></div>"
    )


def _attestation_html(root: Path, t_: Callable[[str], str]) -> str:
    """Chain verification, not a line count: the ledger's whole point is
    that tampering is detectable, so the panel detects it (recomputing the
    sha256 chain is O(entries), fine on a page load)."""
    from ai_venture_studio.adoption.attestation import verify_ledger

    ledger = root / ".mas" / "attestation" / "ledger.jsonl"
    if not ledger.exists():
        # Absence is stated, never omitted — a missing ledger must not read
        # as attested-and-clean.
        return f"<span class=muted>{t_('gov_no_ledger')}</span>"
    try:
        verification = verify_ledger(root)
    except ValueError as exc:
        # An unparseable line is tampering too — render it as broken, don't
        # take the page down.
        return (
            f"<span class=bad>{t_('gov_ledger_broken')} ?</span> — "
            f"{html.escape(str(exc))}"
        )
    if verification.ok:
        return (
            f"{t_('gov_attestations')}: <b>{verification.entries}</b> "
            f"<span class=ok>{t_('gov_ledger_ok')}</span>"
        )
    problems = "; ".join(verification.problems[:3])
    return (
        f"<span class=bad>{t_('gov_ledger_broken')} "
        f"{verification.first_bad_seq}</span> — {html.escape(problems)}"
    )


def _stage_grid_html(root: Path, t_: Callable[[str], str]) -> str:
    from ai_venture_studio.adoption.substrate import (
        STAGE_FLOORS,
        load_substrate_profile,
        stage_activation,
    )

    head = f"<b>{t_('gov_stages')}</b>"
    try:
        profile = load_substrate_profile(root)
    except ValueError as exc:
        # A malformed profile must not take the page down — render it as
        # broken with the loader's own message (it names the field).
        return (
            f"<div class=card>{head}"
            f"<p class=bad>{html.escape(str(exc))}</p></div>"
        )
    if profile is None:
        return (
            f"<div class=card>{head}"
            f"<p class=muted>{t_('gov_no_substrate')}</p>"
            f"<p><code>avs readiness</code></p>"
            f"<p class=muted>{t_('gov_substrate_effect')} "
            f"{t_('gov_action_reload')}</p></div>"
        )
    icons = {"ACTIVE": "✅", "DEGRADED": "⚠️", "STAGE_INACTIVE": "⛔"}
    rows = ""
    for stage in STAGE_FLOORS:
        activation = stage_activation(profile, stage)
        status = str(activation.status.value if hasattr(activation.status, "value")
                     else activation.status)
        note = f" <span class=muted>{html.escape(activation.note)}</span>" \
            if activation.note else ""
        rows += (
            f"<tr><td><code>{html.escape(stage)}</code></td>"
            f"<td>{icons.get(status, '')} {html.escape(status)}</td>"
            f"<td>{html.escape(activation.rung_present)} / "
            f"{html.escape(activation.rung_required)}{note}</td></tr>"
        )
    return (
        f"<div class=card>{head} <span class=muted>"
        f"({html.escape(profile.rung().label)})</span><table>{rows}</table></div>"
    )


def _dwell_html(root: Path, t_: Callable[[str], str]) -> str:
    """The F-18.3 rubber-stamp detector, on the page where the gate owner
    already is. Notes render verbatim — the report's own words, including
    'nothing to measure', are the honest rendering."""
    from ai_venture_studio.adoption.dwell import gate_dwell_report

    report = gate_dwell_report(root)
    stats = ""
    if report.median_s is not None:
        stats = (
            f"<p>{t_('gov_dwell_median')}: <b>{report.median_s:.0f}s</b> · "
            f"p90 {report.p90_s:.0f}s · "
            f"{t_('gov_override_rate')}: {report.override_rate:.0%} · "
            f"n={len(report.samples)}</p>"
        )
    css = "bad" if report.rubber_stamp else "muted"
    notes = "".join(
        f"<p class={css}>{html.escape(note)}</p>" for note in report.notes
    )
    return f"<div class=card><b>{t_('gov_dwell')}</b>{stats}{notes}</div>"


def _automation_html(root: Path, t_: Callable[[str], str]) -> str:
    from ai_venture_studio.automation import (
        AUTOMERGE_POLICY,
        DEPLOY_EXEC_POLICY,
        PolicyError,
        load_policy,
    )

    rows = ""
    for filename in (AUTOMERGE_POLICY, DEPLOY_EXEC_POLICY):
        name = html.escape(filename)
        try:
            policy = load_policy(root, filename)
        except PolicyError as exc:
            rows += (
                f"<tr><td><code>{name}</code></td>"
                f"<td class=bad>{t_('gov_policy_error')}: "
                f"{html.escape(str(exc))}</td></tr>"
            )
            continue
        if policy.enabled:
            rows += (
                f"<tr><td><code>{name}</code></td>"
                f"<td class=warn>{t_('gov_armed')} "
                f"{html.escape(policy.armed_by)} · {t_('gov_expires')} "
                f"{html.escape(policy.expires_at)}</td></tr>"
            )
        else:
            rows += (
                f"<tr><td><code>{name}</code></td>"
                f"<td class=ok>{t_('gov_disarmed')}</td></tr>"
            )
    return (
        f"<div class=card><b>{t_('gov_automation')}</b><table>{rows}</table></div>"
    )
