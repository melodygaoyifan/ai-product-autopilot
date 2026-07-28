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
    return (
        f"<div class=card><b>{t_('h_engineer')}</b>"
        f"<p class=muted>{t_('mode_note_engineer')}</p>"
        f"{profile_line}{table}{hints}</div>"
    )


def enterprise_panel(root: Path, t_: Callable[[str], str]) -> str:
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
        return f"<div class=card>{head}<p class=warn>{t_('gov_no_edition')}</p></div>"

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
    ledger = root / ".mas" / "attestation" / "ledger.jsonl"
    if ledger.exists():
        # Count, don't parse: the panel reports how much has been attested,
        # verification stays with `avs attest`.
        count = sum(
            1 for line in ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        attest = f"{t_('gov_attestations')}: <b>{count}</b>"
    else:
        # Absence is stated, never omitted — a missing ledger must not read
        # as attested-and-clean.
        attest = f"<span class=muted>{t_('gov_no_ledger')}</span>"
    return (
        f"<div class=card>{head}<table>{rows}</table>"
        f"<p>{owner}</p><p>{attest}</p></div>"
    )
