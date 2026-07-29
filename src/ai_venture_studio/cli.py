"""CLI entry point: `avs review <target>`.

Target is a GitHub PR URL (requires `gh` auth) or a local git revision
range such as `main...HEAD`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ai_venture_studio.adoption import StageInactiveError, check_stage
from ai_venture_studio.orchestrator import is_interrupted, resume_review, run_review
from ai_venture_studio.state import Verdict

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()

from ai_venture_studio.paths import skills_root as _skills_root

_DEFAULT_SKILLS = _skills_root()


@app.callback()
def _root() -> None:
    """ai-venture-studio — multi-agent review-side SDLC system."""


@app.command()
def review(
    target: str = typer.Argument(..., help="GitHub PR URL or git range (e.g. main...HEAD)"),
    repo_dir: str = typer.Option(".", help="Repository to review in"),
    skills_dir: str = typer.Option(str(_DEFAULT_SKILLS), help="Voter skills directory"),
    mode: str = typer.Option(None, help="Override mode: fast | standard | deep"),
    provider: str = typer.Option(
        None,
        help="Force one provider for all voters (e.g. 'mock' for offline runs; "
        "heterogeneity is the default posture)",
    ),
):
    # Substrate ladder guard (ADR-U15): no-op unless the workspace declares
    # .mas/substrate-profile.yaml; below-floor stages refuse loudly.
    try:
        check_stage(repo_dir, "code_review")
    except StageInactiveError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("Run `avs readiness` for the rung roadmap.")
        raise typer.Exit(code=4) from exc

    result, state = run_review(
        target,
        repo_dir=repo_dir,
        skills_dir=skills_dir,
        provider_override=provider,
        mode_override=mode,
    )

    if not state.get("dor_pass"):
        console.print("[yellow]Not ready for review (Gate 1 failed):[/yellow]")
        for reason in state.get("dor_reasons", []):
            console.print(f"  - {reason}")
        raise typer.Exit(code=2)

    if is_interrupted(state):
        console.print(
            f"\n[bold red]{state['leader']['verdict']}[/bold red] — paused at "
            "Gate 3 (Review Gate) for human decision."
        )
        if state.get("hitl_issue_url"):
            console.print(f"Issue: {state['hitl_issue_url']}")
        elif state.get("hitl_note"):
            console.print(f"(no issue created: {state['hitl_note']})")
        console.print(
            f"Resume with: avs resume {state['review_id']} "
            f"--decision ack   (or --decision override:REQUEST_CHANGES)"
        )
        raise typer.Exit(code=3)

    assert result is not None
    color = {
        Verdict.APPROVE: "green",
        Verdict.APPROVE_WITH_NOTES: "green",
        Verdict.REQUEST_CHANGES: "yellow",
    }.get(result.verdict, "red")
    console.print(
        f"\n[bold {color}]{result.verdict.value}[/bold {color}] — {result.summary}"
    )
    from ai_venture_studio.adoption import adoption_banners

    for banner in adoption_banners(repo_dir):
        console.print(f"[dim]{banner}[/dim]")

    if result.findings:
        table = Table(show_lines=False)
        table.add_column("Sev")
        table.add_column("Location")
        table.add_column("Finding")
        for f in result.findings:
            table.add_row(
                f.severity.value,
                f"{f.file_path}:{f.line_start}",
                f"{f.title} [{f.voter}]",
            )
        console.print(table)

    console.print(f"\nArtifacts: {state['artifacts_dir']}")
    if result.verdict.is_escalation:
        raise typer.Exit(code=3)


@app.command()
def resume(
    review_id: str = typer.Argument(..., help="Review ID shown when the run paused"),
    decision: str = typer.Option(
        ..., help="'ack' to accept the verdict, or 'override:<VERDICT>'"
    ),
    repo_dir: str = typer.Option(".", help="Repository the review ran in"),
):
    """Continue a review paused at Gate 3 (Review Gate)."""
    result, state = resume_review(review_id, decision, repo_dir=repo_dir)
    assert result is not None
    console.print(
        f"\nResumed with decision [bold]{decision}[/bold] → "
        f"[bold]{result.verdict.value}[/bold] — {result.summary}"
    )
    console.print(f"Artifacts: {state['artifacts_dir']}")


@app.command()
def replay(
    review_id: str = typer.Argument(None, help="Review ID; omit to list reviews"),
    repo_dir: str = typer.Option(".", help="Repository the review ran in"),
    demo: bool = typer.Option(
        False, "--demo",
        help="Replay the vendored demo review offline — no API key, no "
             "workspace: proves the audit trail is real before you trust "
             "us with a key (doc 25 §73.1, rung R1)"),
):
    """Replay a past review's audit trail from its YAML mirror."""
    from ai_venture_studio.replay import load_replay, summarize_step

    if demo:
        from ai_venture_studio.editions import EDITIONS_ROOT

        reviews_dir = EDITIONS_ROOT / "demo" / "reviews"
        review_id = review_id or next(
            p.name for p in sorted(reviews_dir.iterdir()) if p.is_dir()
        )
        console.print("[dim]offline demo bundle — a real review of this repo's "
                      "own code, redacted; every step below was written by the "
                      "pipeline at run time[/dim]")
    else:
        reviews_dir = Path(repo_dir) / ".mas" / "reviews"
    if review_id is None:
        rows = sorted(p.name for p in reviews_dir.iterdir() if p.is_dir())
        for name in rows:
            console.print(name)
        if not rows:
            console.print("(no reviews recorded)")
        return

    rep = load_replay(reviews_dir, review_id)
    table = Table(show_lines=False, title=f"review {rep.review_id}")
    table.add_column("#")
    table.add_column("node")
    table.add_column("at")
    table.add_column("summary")
    for step in rep.steps:
        table.add_row(
            str(step.step),
            step.node,
            step.written_at.strftime("%H:%M:%S"),
            summarize_step(step),
        )
    console.print(table)
    console.print(
        f"verdict: [bold]{rep.verdict}[/bold]"
        + (f" · {rep.duration_s:.1f}s" if rep.duration_s is not None else "")
    )


@app.command()
def compound(
    repo_dir: str = typer.Option(".", help="Repository whose review record to aggregate"),
    days: int = typer.Option(7, help="Signal window in days"),
    provider: str = typer.Option("anthropic", help="Proposer provider"),
    model: str = typer.Option("claude-opus-4-8", help="Proposer model"),
    pr: bool = typer.Option(
        False, "--pr", help="Open a CLAUDE.md update PR (human still merges)"
    ),
):
    """Weekly compounding loop: aggregate review signals, propose CLAUDE.md
    constraints, optionally open the human-gated update PR (§09.8)."""
    import datetime
    import subprocess

    from ai_venture_studio import compound as comp

    date = datetime.date.today().isoformat()
    signals = comp.collect_signals(repo_dir, days=days)
    proposals = comp.propose(signals, provider=provider, model=model)
    report = comp.render_proposal(signals, proposals, date=date)

    out_dir = Path(repo_dir) / ".mas" / "compound"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"proposal-{date}.md"
    report_path.write_text(report, encoding="utf-8")
    console.print(report)
    console.print(f"\nProposal written to {report_path}")

    if not proposals:
        raise typer.Exit(code=0)
    if not pr:
        console.print("Re-run with --pr to open the CLAUDE.md update PR.")
        raise typer.Exit(code=0)

    branch = f"avs/compound-{date}"
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=repo_dir, capture_output=True, text=True
        )

    git("checkout", "-B", branch)
    comp.apply_to_claude_md(repo_dir, proposals, date=date)
    git("add", "CLAUDE.md")
    git("commit", "-m", f"compound: propose {len(proposals)} CLAUDE.md constraint(s) ({date})")
    push = git("push", "-u", "origin", branch)
    if push.returncode != 0:
        console.print(f"[yellow]push failed: {push.stderr.strip()[:200]}[/yellow]")
        raise typer.Exit(code=1)
    created = subprocess.run(
        [
            "gh", "pr", "create",
            "--title", f"[compound] CLAUDE.md constraints — {date}",
            "--body", report + "\n\n🤖 opened by the avs compounding loop",
        ],
        cwd=repo_dir, capture_output=True, text=True,
    )
    output = (created.stdout or created.stderr).strip()
    git("checkout", "-")
    if created.returncode != 0:
        console.print(f"[yellow]gh pr create failed: {output[:200]}[/yellow]")
        raise typer.Exit(code=1)
    console.print(output.splitlines()[-1] if output else "(no gh output)")


_DEFAULT_CASES = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "cases"


@app.command()
def bench(
    cases_dir: str = typer.Option(str(_DEFAULT_CASES), help="Labeled benchmark cases"),
    skills_dir: str = typer.Option(str(_DEFAULT_SKILLS), help="Voter skills directory"),
    provider: str = typer.Option(None, help="Force one provider (e.g. 'mock')"),
    limit: int = typer.Option(None, help="Run only the first N cases"),
    repo_dir: str = typer.Option(".", help="Where to record the result"),
):
    """Run the labeled benchmark; v0.1.0 bars: recall >=40%, precision >=50%."""
    from ai_venture_studio.bench import run_benchmark, save_result

    result = run_benchmark(
        cases_dir, skills_dir=skills_dir, provider_override=provider, limit=limit
    )
    table = Table(title="benchmark")
    for col in ("case", "verdict", "recall", "findings (matched)", "s"):
        table.add_column(col)
    for c in result.cases:
        table.add_row(
            c.name,
            c.verdict,
            f"{c.expected_matched}/{c.expected_total}",
            f"{c.findings_total} ({c.findings_matched})",
            str(c.duration_s),
        )
    console.print(table)
    verdict = "PASS" if result.passes() else "FAIL"
    console.print(
        f"recall [bold]{result.recall:.0%}[/bold] (bar 40%) · "
        f"precision [bold]{result.precision:.0%}[/bold] (bar 50%) → [bold]{verdict}[/bold]"
    )
    console.print(f"saved: {save_result(result, repo_dir)}")
    if not result.passes():
        raise typer.Exit(code=1)


_DEPLOY_SKILLS = _skills_root() / "deploy"


@app.command("deploy-review")
def deploy_review(
    target: str = typer.Argument(..., help="GitHub PR URL or git range"),
    repo_dir: str = typer.Option(".", help="Repository to review in"),
    skills_dir: str = typer.Option(str(_DEPLOY_SKILLS), help="Deploy voter skills"),
    provider: str = typer.Option(None, help="Force one provider (e.g. 'mock')"),
):
    """Gate 5 — Deployment Review MAS (§09.11). Recommends; never deploys."""
    from ai_venture_studio.deploy import run_deploy_review

    try:
        activation = check_stage(repo_dir, "deploy_review")
    except StageInactiveError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("Run `avs readiness` for the rung roadmap.")
        raise typer.Exit(code=4) from exc
    lint_only = activation is not None and activation.status.value == "DEGRADED"
    if lint_only:
        console.print(f"[yellow]deploy_review DEGRADED — {activation.note}[/yellow]")

    result = run_deploy_review(
        target, repo_dir=repo_dir, skills_dir=skills_dir,
        provider_override=provider, lint_only=lint_only,
    )
    color = "green" if result.verdict.value == "PROMOTE" else (
        "yellow" if result.verdict.value == "HOLD_FOR_HUMAN" else "red"
    )
    console.print(f"\n[bold {color}]{result.verdict.value}[/bold {color}] — {result.summary}")
    if result.findings:
        table = Table(show_lines=False)
        for col in ("Sev", "Location", "Finding"):
            table.add_column(col)
        for f in result.findings:
            table.add_row(
                f.severity.value, f"{f.file_path}:{f.line_start}", f"{f.title} [{f.voter}]"
            )
        console.print(table)
    console.print(f"Artifacts: {result.artifacts_dir}")
    if result.verdict.value.startswith("ESCALATE_"):
        raise typer.Exit(code=3)


@app.command()
def triage(
    incident_file: str = typer.Argument(..., help="Incident file (.json/.yaml/.txt)"),
    repo_dir: str = typer.Option(".", help="Repository to correlate against"),
    provider: str = typer.Option("anthropic", help="Provider (e.g. 'mock')"),
    days: int = typer.Option(7, help="Correlation window for recent commits"),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Assistive tier: attempt a fix-PR when a root cause is proposed "
        "(this flag IS the human approval; the PR still re-enters code review)",
    ),
):
    """Gate 6 intake — Maintenance MAS (§09.12): triage + root-cause."""
    # Substrate ladder guard (ADR-U15): a stage below its
    # infrastructure floor is inactive-never-degraded. No-op unless the
    # workspace declares .mas/substrate-profile.yaml.
    try:
        check_stage(repo_dir, "maintenance")
    except StageInactiveError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("Run `avs readiness` for the rung roadmap.")
        raise typer.Exit(code=4) from exc
    from ai_venture_studio.maintenance import Incident, run_maintenance

    incident = Incident.load(incident_file)
    result = run_maintenance(
        incident, repo_dir=repo_dir, provider=provider, days=days
    )
    color = {
        "TRIAGED_LOW_PRIORITY": "green",
        "ROOT_CAUSE_PROPOSED": "yellow",
    }.get(result.verdict.value, "red")
    console.print(f"\n[bold {color}]{result.verdict.value}[/bold {color}] — {result.summary}")
    if result.root_cause:
        console.print(f"hypothesis: {result.root_cause.hypothesis}")
        console.print(f"next action: {result.root_cause.next_action}")
    if result.suspects:
        console.print("suspects: " + ", ".join(s["sha"] for s in result.suspects))
    console.print(f"Artifacts: {result.artifacts_dir}")

    if fix and result.verdict.value == "ROOT_CAUSE_PROPOSED":
        from ai_venture_studio.maintenance.fixpr import generate_fix_pr

        attempt = generate_fix_pr(
            incident, result.root_cause, repo_dir=repo_dir, provider=provider
        )
        console.print(
            f"\nfix attempt: [bold]{attempt.status}[/bold]"
            + (f" · branch {attempt.branch}" if attempt.branch else "")
            + (f" · {attempt.pr_url}" if attempt.pr_url else "")
        )
        if attempt.detail:
            console.print(f"  {attempt.detail}")
        if attempt.files_changed:
            console.print(f"  files: {', '.join(attempt.files_changed)}")
    elif fix:
        console.print("\nfix attempt skipped: no root cause proposed")

    if result.verdict.value.startswith("ESCALATE_"):
        raise typer.Exit(code=3)


@app.command("deploy-outcome")
def deploy_outcome(
    review_id: str = typer.Argument(..., help="Deploy review ID"),
    outcome: str = typer.Option(..., help="'correct' or 'incorrect'"),
    repo_dir: str = typer.Option(".", help="Repository the review ran in"),
):
    """Record the human verdict on a past deploy recommendation (§09.11.5).
    Streaks of correct PROMOTEs make the stage eligible for assistive tier."""
    from ai_venture_studio.deploy import track_record

    if not track_record.mark_outcome(repo_dir, review_id, outcome):
        console.print(f"[red]no deploy review {review_id!r} on record[/red]")
        raise typer.Exit(code=1)
    ready = track_record.readiness(repo_dir)
    console.print(
        f"recorded. streak: {ready.streak}/{ready.needed} correct PROMOTEs"
        + (" — [bold]eligible for assistive tier[/bold]" if ready.eligible else "")
    )


@app.command()
def serve(
    repo_dir: str = typer.Option(".", help="Repository the server operates on"),
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8422, help="Port"),
):
    """Webhook mode: GitHub PR events -> reviews, incident POSTs -> triage.
    Requires AUTOPRODUCT_WEBHOOK_SECRET for signature verification."""
    from ai_venture_studio.server import serve as run_server

    run_server(repo_dir, host=host, port=port)


@app.command()
def worker(
    repo_dir: str = typer.Option(".", help="Repository the worker operates on"),
    queue_db: str = typer.Option(
        ".mas/queue.db", help="SQLite queue (same path the server enqueues to)"
    ),
    max_jobs: int = typer.Option(
        0, help="Exit after N jobs (0 = run forever); nonzero also exits when idle"
    ),
):
    """Queue worker: drains jobs the server enqueued when
    AUTOPRODUCT_QUEUE_DB is set. Run several for parallel throughput on
    one host; multi-host needs a shared broker (see jobqueue docstring)."""
    from ai_venture_studio.jobqueue import worker_loop

    done = worker_loop(queue_db, repo_dir, max_jobs=max_jobs or None)
    console.print(f"worker exited after {done} job(s)")


@app.command()
def init(
    directory: str = typer.Argument(..., help="Workspace directory to create"),
    name: str = typer.Option(None, help="Project name (defaults to directory name)"),
    profile: str = typer.Option(..., help="Domain profile: web | miniprogram | app"),
    edition: str = typer.Option(
        None, help="Edition preset: enterprise | solo | engineer (doc 24; "
                   "narrowing-only, linted at init)"),
    gate_owner: str = typer.Option(
        None, help="Named human per gate class — required by the enterprise "
                   "edition (§69.1)"),
    from_bench: str = typer.Option(
        None, "--from-bench",
        help="Seed FDR.md from a product-bench case (e.g. 01-groupbuy-api) — "
             "templates are the same fixtures the benchmark runs, so a "
             "template that rots fails CI, not you (doc 25 §73.2)"),
):
    """Create a greenfield workspace: profile constraints, CLAUDE.md, specs/."""
    from ai_venture_studio.upstream import init_workspace

    resolved_edition = None
    if edition:
        import yaml as _yaml

        from ai_venture_studio.editions import EditionError, load_edition_preset

        try:
            resolved_edition = load_edition_preset(edition)
        except EditionError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=2) from exc
        if resolved_edition.get("gate_policy", {}).get(
            "require_gate_owner"
        ) and not gate_owner:
            console.print(
                "[red]edition 'enterprise' requires --gate-owner: a named human "
                "per gate class is the 12%-conversion profile, enforced at init "
                "(§69.1)[/red]"
            )
            raise typer.Exit(code=2)

    root = init_workspace(directory, name or Path(directory).name, profile)
    if from_bench:
        import yaml as _yaml

        bench_root = Path(__file__).resolve().parents[2] / "benchmarks"
        case = next(
            (p for sub in ("products-real", "products")
             for p in [bench_root / sub / f"{from_bench}.yaml"] if p.exists()),
            None,
        )
        if case is None:
            console.print(f"[red]no bench case named {from_bench!r}[/red]")
            raise typer.Exit(code=2)
        fdr = str((_yaml.safe_load(case.read_text()) or {}).get("fdr", ""))
        (Path(root) / "FDR.md").write_text(fdr, encoding="utf-8")
        console.print(f"FDR.md seeded from bench case {from_bench}")
    if resolved_edition:
        import yaml as _yaml

        if gate_owner:
            resolved_edition["gate_policy"]["gate_owner"] = gate_owner
        target = Path(root) / ".mas" / "edition.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_yaml.safe_dump(resolved_edition, sort_keys=False))
        console.print(
            f"edition [bold]{edition}[/bold] resolved → {target} · start at "
            f"{resolved_edition.get('docs_entry', 'editions/')}"
        )
    console.print(f"workspace ready: {root}")
    console.print(
        f"next: avs spec \"<what you want to build>\" --repo-dir {root}"
    )


@app.command()
def spec(
    request: str = typer.Argument(..., help="What you want to build, in plain words"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider (e.g. 'mock')"),
):
    """Spec stage: EARS criteria + test skeletons, linted and critiqued."""
    # Substrate ladder guard (ADR-U15): a stage below its
    # infrastructure floor is inactive-never-degraded. No-op unless the
    # workspace declares .mas/substrate-profile.yaml.
    try:
        check_stage(repo_dir, "specification")
    except StageInactiveError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("Run `avs readiness` for the rung roadmap.")
        raise typer.Exit(code=4) from exc
    from ai_venture_studio.upstream import run_spec_stage

    result = run_spec_stage(repo_dir, request, provider=provider)
    color = {"proposed": "green", "blocked": "red"}.get(result.status, "yellow")
    console.print(
        f"\n[bold {color}]{result.status}[/bold {color}] — {result.title} "
        f"({len(result.criteria)} criteria, {result.revisions} revision(s))"
    )
    for i, criterion in enumerate(result.criteria):
        console.print(f"  {i}. {criterion}")
    if result.lint_issues:
        console.print(f"[red]lint issues: {result.lint_issues}[/red]")
    console.print(f"spec: {Path(repo_dir) / 'specs' / result.slug / 'spec.md'}")
    if result.status == "proposed":
        console.print(
            f"Gate U3: avs spec-approve {result.slug} --repo-dir {repo_dir}"
        )


@app.command("spec-approve")
def spec_approve(
    slug: str = typer.Argument(..., help="Spec slug"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
):
    """Gate U3 — human approval that makes a spec buildable."""
    from ai_venture_studio.upstream import approve_spec

    result = approve_spec(repo_dir, slug)
    console.print(
        f"approved: {result.title}\n"
        f"next: avs build {slug} --repo-dir {repo_dir}"
    )


@app.command()
def build(
    slug: str = typer.Argument(..., help="Approved spec slug"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider (e.g. 'mock')"),
    review: bool = typer.Option(
        True, help="Run the review pipeline on the built commit"
    ),
):
    """Coding stage: test-first implementation of an approved spec; the
    commit is handed to the review pipeline (Gate U4 -> Gate 1)."""
    # Substrate ladder guard (ADR-U15): a stage below its
    # infrastructure floor is inactive-never-degraded. No-op unless the
    # workspace declares .mas/substrate-profile.yaml.
    try:
        check_stage(repo_dir, "coding")
    except StageInactiveError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("Run `avs readiness` for the rung roadmap.")
        raise typer.Exit(code=4) from exc
    from ai_venture_studio.upstream import run_build

    result = run_build(repo_dir, slug, provider=provider)
    color = {"built": "green"}.get(result.status, "red")
    console.print(
        f"\n[bold {color}]{result.status}[/bold {color}] — {result.iterations} "
        f"iteration(s); {len(result.files_written)} file(s); {result.test_summary}"
    )
    if result.detail:
        console.print(result.detail)
    if result.status != "built":
        raise typer.Exit(code=1)
    console.print(f"commit {result.commit}: {', '.join(result.files_written)}")
    if review:
        console.print("\nhanding to review stage (avs review HEAD~1)…")
        review_result, state = run_review(
            "HEAD~1..HEAD",
            repo_dir=repo_dir,
            skills_dir=str(_DEFAULT_SKILLS),
            provider_override=provider if provider == "mock" else None,
        )
        if review_result:
            console.print(
                f"review verdict: [bold]{review_result.verdict.value}[/bold] — "
                f"{review_result.summary}"
            )


@app.command()
def discover(
    idea: str = typer.Argument(..., help="Your product idea, in plain words"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider (e.g. 'mock')"),
):
    """Discovery stage: evidence-tagged ProductBrief + hypothesis ledger."""
    # Substrate ladder guard (ADR-U15): a stage below its
    # infrastructure floor is inactive-never-degraded. No-op unless the
    # workspace declares .mas/substrate-profile.yaml.
    try:
        check_stage(repo_dir, "discovery")
    except StageInactiveError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("Run `avs readiness` for the rung roadmap.")
        raise typer.Exit(code=4) from exc
    from ai_venture_studio.upstream import run_discovery

    brief = run_discovery(repo_dir, idea, provider=provider)
    console.print(f"\n[bold]{brief.title}[/bold] — {brief.status}")
    for h in brief.hypotheses:
        console.print(f"  ({h.evidence}) {h.statement}")
    console.print(f"scope_now: {brief.scope_now}")
    console.print(f"brief: {Path(repo_dir) / 'product' / 'brief.md'}")
    console.print("Gate U1: avs brief-approve")


@app.command("brief-approve")
def brief_approve(repo_dir: str = typer.Option(".", help="Workspace directory")):
    """Gate U1 — the human problem-selection decision."""
    from ai_venture_studio.upstream import approve_brief

    brief = approve_brief(repo_dir)
    console.print(f"approved: {brief.title}\nnext: avs plan")


@app.command()
def plan(
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider (e.g. 'mock')"),
):
    """Planning stage: task DAG from the approved brief (dag-checked)."""
    # Substrate ladder guard (ADR-U15): a stage below its
    # infrastructure floor is inactive-never-degraded. No-op unless the
    # workspace declares .mas/substrate-profile.yaml.
    try:
        check_stage(repo_dir, "planning")
    except StageInactiveError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("Run `avs readiness` for the rung roadmap.")
        raise typer.Exit(code=4) from exc
    from ai_venture_studio.upstream import run_planning

    result = run_planning(repo_dir, provider=provider)
    color = {"proposed": "green", "blocked": "red"}.get(result.status, "yellow")
    console.print(f"\n[bold {color}]{result.status}[/bold {color}] — {len(result.tasks)} task(s)")
    for t in result.tasks:
        deps = f" <- {','.join(t.depends_on)}" if t.depends_on else ""
        console.print(f"  {t.id} [{t.lane}] {t.title}{deps} ({t.estimate_hours}h)")
    if result.dag_issues:
        console.print(f"[red]dag issues: {result.dag_issues}[/red]")
    if result.status == "proposed":
        console.print("Gate U2 (scope lock): avs plan-approve")


@app.command("plan-approve")
def plan_approve(repo_dir: str = typer.Option(".", help="Workspace directory")):
    """Gate U2 — lock scope; changes after this go through an SCR."""
    from ai_venture_studio.upstream import approve_plan, next_tasks

    plan_result = approve_plan(repo_dir)
    ready = next_tasks(repo_dir)
    console.print(f"scope locked: {len(plan_result.tasks)} task(s)")
    for t in ready:
        console.print(f"  ready: {t.id} — avs spec \"{t.description}\"")


@app.command()
def create(
    directory: str = typer.Argument(..., help="Where your product lives (created if new)"),
    profile: str = typer.Option(..., help="web | miniprogram | app"),
    fdr: str = typer.Option(None, help="Your FDR file (default: <dir>/FDR.md)"),
    yes: bool = typer.Option(False, "--yes", help="Confirm the plan and build everything"),
    provider: str = typer.Option("anthropic", help="Provider (e.g. 'mock')"),
):
    """The non-technical flow: write ONE document (the FDR), the system
    builds the product. First run writes the FDR template + guide."""
    from ai_venture_studio.upstream import init_workspace
    from ai_venture_studio.upstream.autopilot import run_autopilot
    from ai_venture_studio.upstream.fdr import write_template

    root = Path(directory).resolve()
    if not (root / ".mas" / "project.yaml").exists():
        init_workspace(root, root.name, profile)
    fdr_path = Path(fdr) if fdr else root / "FDR.md"
    if not fdr_path.exists() or not fdr_path.read_text(encoding="utf-8").strip():
        write_template(root)
        console.print(
            f"第一步：用自己的话填写 {root / 'FDR.md'}（参考 {root / 'FDR-GUIDE.md'}），"
            f"然后重新运行这条命令。\n"
            f"Step 1: fill in {root / 'FDR.md'} in your own words (see FDR-GUIDE.md), "
            f"then run this command again."
        )
        return

    result = run_autopilot(root, fdr_path, provider=provider, yes=yes)
    if result.status == "needs_answers":
        console.print("[yellow]还需要一些信息 / A few answers needed:[/yellow]")
        for i, q in enumerate(result.assessment.questions, 1):
            console.print(f"  {i}. {q}")
        console.print(f"详见 {root / 'FDR-QUESTIONS.md'} — 补充进 FDR.md 后重新运行。")
        raise typer.Exit(code=2)
    if result.status == "awaiting_confirmation":
        console.print(result.confirmation)
        console.print(f"\n(saved to {root / 'product' / 'CONFIRMATION.md'})")
        raise typer.Exit(code=0)
    color = "green" if result.status == "completed" else "red"
    console.print(f"\n[bold {color}]{result.status}[/bold {color}]")
    for o in result.outcomes:
        verdict = f" · review: {o.review_verdict}" if o.review_verdict else ""
        console.print(f"  {o.task_id} {o.title}: {o.status}{verdict}")
    console.print(f"报告 / report: {result.report_path}")
    if result.status != "completed":
        raise typer.Exit(code=1)


@app.command()
def studio(
    # Positional, like init/create — every doc writes `avs studio myteam`,
    # and the option form made that documented invocation an error.
    repo_dir: str = typer.Argument(".", help="Workspace directory"),
    # `--repo-dir` was the only way in before, and the CLI surface is a
    # versioned contract (CONTRIBUTING): it keeps working rather than
    # breaking whatever already scripted it.
    repo_dir_opt: str = typer.Option(
        None, "--repo-dir", hidden=True,
        help="Deprecated: pass the workspace positionally instead.",
    ),
    port: int = typer.Option(8433, help="Port"),
    profile: str = typer.Option(None, help="Profile (only needed for a new workspace)"),
    lang: str = typer.Option(
        "en", help="UI language: en (English, default) | zh (bilingual "
                   "Chinese-first). Your FDR may be written in either "
                   "language whichever UI you choose."
    ),
    mode: str = typer.Option(
        None, help="UI mode: founder | engineer | enterprise. Default: "
                   "resolved from the workspace edition (.mas/edition.yaml"
                   " — solo→founder), else founder. Modes only add "
                   "read-only detail; the flow is the same in all three."
    ),
):
    """Founder Studio: the browser UI for the FDR flow (localhost only)."""
    from ai_venture_studio.studio import serve_studio
    from ai_venture_studio.studio_modes import StudioModeError
    from ai_venture_studio.upstream import init_workspace

    if repo_dir_opt is not None:
        if repo_dir not in (".", repo_dir_opt):
            console.print(
                "[red]workspace given twice: "
                f"{repo_dir!r} and --repo-dir {repo_dir_opt!r}[/red]"
            )
            raise typer.Exit(code=2)
        console.print(
            "[yellow]--repo-dir is deprecated for `studio`; "
            "pass the workspace positionally: avs studio <dir>[/yellow]"
        )
        repo_dir = repo_dir_opt
    root = Path(repo_dir).resolve()
    if not (root / ".mas" / "project.yaml").exists():
        if not profile:
            console.print("[red]new workspace: pass --profile web|miniprogram|app[/red]")
            raise typer.Exit(code=2)
        init_workspace(root, root.name, profile)
    console.print(f"Studio: http://127.0.0.1:{port}  (workspace: {root})")
    try:
        serve_studio(root, port=port, lang=lang, mode=mode)
    except StudioModeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc


@app.command()
def preview(
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    port: int = typer.Option(8500, help="Port for the app"),
):
    """Run the built product locally so the founder can try it (web profile)."""
    import subprocess

    from ai_venture_studio.upstream import load_project

    root = Path(repo_dir).resolve()
    project = load_project(root)
    if project.profile == "miniprogram":
        console.print(
            "小程序预览：用微信开发者工具打开这个目录即可（工具 → 导入项目）：\n"
            f"  {root}\n"
            "Open this directory in WeChat DevTools (import project) to preview."
        )
        return
    from ai_venture_studio.upstream.provisioning import preview_env

    for entry in ("app/main.py", "main.py", "app.py"):
        candidate = root / entry
        if candidate.exists():
            console.print(f"starting {entry} — http://127.0.0.1:{port}  (Ctrl-C stops)")
            subprocess.run(
                [sys.executable, str(candidate)],
                cwd=root,
                env={**__import__("os").environ, "PORT": str(port), **preview_env(root)},
            )
            return
    console.print("[yellow]no runnable entry found (looked for app/main.py, main.py, app.py)[/yellow]")
    raise typer.Exit(code=1)


@app.command()
def add(
    fdr: str = typer.Argument(..., help="Feature FDR file (one feature per FDR)"),
    repo_dir: str = typer.Option(".", help="Existing workspace"),
    yes: bool = typer.Option(False, "--yes", help="Confirm and build the feature"),
    provider: str = typer.Option("anthropic", help="Provider (e.g. 'mock')"),
):
    """Add ONE feature to an existing product from a granular FDR. Keep each
    FDR small: one feature or change per document."""
    from ai_venture_studio.upstream.autopilot import run_feature

    result = run_feature(repo_dir, fdr, provider=provider, yes=yes)
    if result.status == "needs_answers":
        for i, q in enumerate(result.assessment.questions, 1):
            console.print(f"  {i}. {q}")
        raise typer.Exit(code=2)
    if result.status == "awaiting_confirmation":
        console.print(result.confirmation)
        console.print("re-run with --yes to build this feature")
        raise typer.Exit(code=0)
    color = "green" if result.status == "completed" else "red"
    console.print(f"\n[bold {color}]{result.status}[/bold {color}]")
    for o in result.outcomes:
        verdict = f" · review: {o.review_verdict}" if o.review_verdict else ""
        console.print(f"  {o.task_id} {o.title}: {o.status}{verdict}")
    if result.report_path:
        console.print(f"report: {result.report_path}")
    if result.status != "completed":
        raise typer.Exit(code=1)


@app.command()
def scr(
    slug: str = typer.Argument(..., help="Built spec slug that needs changing"),
    reason: str = typer.Argument(..., help="Why the spec must change"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
):
    """Raise a Spec Change Request — the only legal way to change a built
    spec (ADR-U02). A human approves it with scr-approve."""
    from ai_venture_studio.upstream.spec import raise_scr

    path = raise_scr(repo_dir, slug, reason)
    console.print(f"raised: {path.name}\napprove with: avs scr-approve {path.stem.split('-')[1]}")


@app.command("scr-approve")
def scr_approve(
    number: int = typer.Argument(..., help="SCR number"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
):
    """Approve an SCR — grants exactly one regeneration of the named spec."""
    from ai_venture_studio.upstream.spec import approve_scr

    data = approve_scr(repo_dir, number)
    console.print(
        f"approved SCR-{number:03d} for spec {data['spec_slug']!r}: {data['reason']}\n"
        f"the next `avs spec`/`add` touching it may now regenerate it once"
    )


@app.command()
def ship(
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    push: bool = typer.Option(
        False, "--push",
        help="Web only: actually deploy via Railway (requires railway login; "
        "this flag IS your deploy decision)",
    ),
):
    """Generate deployment artifacts + a plain-language DEPLOY.md. The
    deploy button stays yours — --push is you pressing it."""
    from ai_venture_studio.upstream.ship import push_web, ship as run_ship

    guide = run_ship(repo_dir)
    console.print(f"部署指南已生成 / deploy guide written: {guide}")
    if push:
        result = push_web(repo_dir)
        color = {"deployed": "green"}.get(result["status"], "yellow")
        console.print(f"[bold {color}]{result['status']}[/bold {color}] — {result['detail']}")
        if result["status"] == "error":
            raise typer.Exit(code=1)


@app.command("product-bench")
def product_bench(
    cases_dir: str = typer.Option(
        str(Path(__file__).resolve().parent.parent.parent / "benchmarks" / "products"),
        help="Labeled product cases (FDR + independent behavioral probes)",
    ),
    provider: str = typer.Option(None, help="Provider (e.g. 'mock')"),
    limit: int = typer.Option(None, help="Run only the first N cases"),
    repo_dir: str = typer.Option(".", help="Where to record the result"),
):
    """Built-product quality, end to end: full autopilot per case, then
    INDEPENDENT probes against the built product (WebGen-Bench pattern)."""
    from ai_venture_studio.product_bench import run_product_bench, save_summary

    try:
        summary = run_product_bench(
            cases_dir, provider=provider, limit=limit, repo_dir=repo_dir
        )
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    table = Table(title="product bench")
    for col in ("case", "autopilot", "built", "probes passed", "clean reviews", "s"):
        table.add_column(col)
    for c in summary.cases:
        table.add_row(
            c.name,
            c.autopilot_status,
            f"{c.tasks_built}/{c.tasks_total}",
            f"{sum(1 for p in c.probes if p.passed)}/{len(c.probes)}",
            f"{c.clean_reviews}/{c.tasks_built}",
            str(c.duration_s),
        )
    console.print(table)
    console.print(
        f"build rate [bold]{summary.build_rate:.0%}[/bold] · "
        f"probe pass [bold]{summary.probe_pass_rate:.0%}[/bold] · "
        f"clean reviews [bold]{summary.clean_review_rate:.0%}[/bold]"
    )
    console.print(f"saved: {save_summary(summary, repo_dir)}")


@app.command()
def recover(repo_dir: str = typer.Option(".", help="Repository the reviews ran in")):
    """Continue reviews, deploy reviews, and incidents that crashed mid-run
    from their checkpoints (all three graphs share .mas/checkpoints.db)."""
    from ai_venture_studio.deploy import recover_deploy_reviews
    from ai_venture_studio.maintenance import recover_maintenance
    from ai_venture_studio.orchestrator import recover_reviews

    results = [
        {"kind": "review", "id": r["review_id"], **{k: v for k, v in r.items()
                                                    if k != "review_id"}}
        for r in recover_reviews(repo_dir)
    ]
    results += recover_deploy_reviews(repo_dir)
    results += recover_maintenance(repo_dir)
    if not results:
        console.print("nothing to recover")
        return
    for r in results:
        console.print(f"  {r['kind']} {r['id']}: {r['status']}"
                      + (f" → {r.get('verdict')}" if r.get("verdict") else ""))


@app.command()
def correct(
    complaint: str = typer.Argument(..., help="What's wrong, in your own words"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider (e.g. 'mock')"),
):
    """M3 — 这不是我要的: repairs go through the fix path, scope changes
    raise an SCR (your complaint IS the approval, recorded verbatim)."""
    from ai_venture_studio.upstream.correction import run_correction

    result = run_correction(repo_dir, complaint, provider=provider)
    color = {"fixed": "green", "scr_raised": "yellow"}.get(result.status, "red")
    console.print(f"[bold {color}]{result.status}[/bold {color}] — {result.detail}")
    if result.status == "error":
        raise typer.Exit(code=1)


@app.command()
def walkthrough(
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider"),
):
    """M4 — regenerate the 验收清单 (product/ACCEPTANCE.md)."""
    from ai_venture_studio.upstream.walkthrough import generate_walkthrough

    console.print(f"written: {generate_walkthrough(repo_dir, provider=provider)}")


@app.command()
def digest(
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider"),
    days: int = typer.Option(7, help="Window"),
):
    """M5 — weekly plain-language digest from the product's own telemetry;
    reconciles the hypothesis ledger with observed events."""
    from ai_venture_studio.upstream.telemetry import generate_digest

    console.print(f"written: {generate_digest(repo_dir, provider=provider, days=days)}")


@app.command("retry-task")
def retry_task(
    task_id: str = typer.Argument(..., help="Failed task id from the report"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider"),
):
    """M7 — retry ONE failed module without rebuilding anything else."""
    from ai_venture_studio.upstream import approve_spec, run_build, run_spec_stage
    from ai_venture_studio.upstream.plan import load_plan

    plan_result = load_plan(repo_dir)
    task = next((t for t in plan_result.tasks if t.id == task_id), None)
    if task is None:
        console.print(f"[red]no task {task_id!r} in the plan[/red]")
        raise typer.Exit(code=1)
    spec = run_spec_stage(repo_dir, f"{task.description} (task:{task.id})", provider=provider)
    if spec.status != "proposed":
        console.print(f"[red]spec blocked: {spec.lint_issues}[/red]")
        raise typer.Exit(code=1)
    approve_spec(repo_dir, spec.slug)
    result = run_build(repo_dir, spec.slug, provider=provider,
                       task_lane=task.lane, task_estimate_hours=task.estimate_hours)
    color = "green" if result.status == "built" else "red"
    console.print(f"[bold {color}]{result.status}[/bold {color}] {result.detail}")
    if result.status != "built":
        raise typer.Exit(code=1)


@app.command()
def undo(repo_dir: str = typer.Option(".", help="Workspace directory")):
    """M7 — 回到上一个版本 (a rescue branch keeps even undo undoable)."""
    from ai_venture_studio.upstream.autopilot import undo_last

    result = undo_last(Path(repo_dir).resolve())
    console.print(f"{result['status']}: {result.get('detail') or result.get('restored_to', '')}")
    if result["status"] == "error":
        raise typer.Exit(code=1)


@app.command()
def verify(
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider"),
):
    """Auto-verify the built product against YOUR FDR: probes are generated
    from what you asked for and run against what was built."""
    from ai_venture_studio.upstream.probegen import verify_product

    path = verify_product(repo_dir, provider=provider)
    console.print(path.read_text(encoding="utf-8"))
    console.print(f"saved: {path}")


@app.command("setup-tests")
def setup_tests(repo_dir: str = typer.Option(".", help="Workspace directory")):
    """小程序: install jest + miniprogram-simulate so page-level tests run
    in the build/test gates (npm required)."""
    from ai_venture_studio.upstream.ship import setup_miniprogram_tests

    result = setup_miniprogram_tests(repo_dir)
    color = {"ready": "green"}.get(result["status"], "yellow")
    console.print(f"[bold {color}]{result['status']}[/bold {color}] — {result['detail']}")


@app.command("services-cloud")
def services_cloud(repo_dir: str = typer.Option(".", help="Workspace directory")):
    """Attempt cloud AUTO-provisioning (Supabase CLI, gated on login);
    degrades to the guided SERVICES.md path when tooling is absent."""
    from ai_venture_studio.upstream import load_project
    from ai_venture_studio.upstream.provisioning import auto_provision_cloud, write_cloud_guide

    profile = load_project(repo_dir).profile
    write_cloud_guide(repo_dir, profile)
    result = auto_provision_cloud(repo_dir, profile)
    color = {"provisioned": "green"}.get(result["status"], "yellow")
    console.print(f"[bold {color}]{result['status']}[/bold {color}] — {result['detail']}")


@app.command()
def readiness(repo_dir: str = typer.Option(".", help="Workspace directory")):
    """Substrate readiness report (docs 18-19): active stages at the
    declared rung and what each missing rung would unlock."""
    from ai_venture_studio.adoption import load_substrate_profile, readiness_report

    profile = load_substrate_profile(repo_dir)
    if profile is None:
        console.print(
            "No .mas/substrate-profile.yaml — the adoption ladder is not "
            "declared, so every stage runs ungated (effective S4).\n"
            "Declare one to get a rung-by-rung modernization roadmap (§18.47.1)."
        )
        raise typer.Exit(code=0)
    console.print(readiness_report(profile, project_name=Path(repo_dir).resolve().name))


@app.command()
def toolchain(
    language: str = typer.Argument(..., help="Language lane: python | java | dotnet"),
    repo_dir: str = typer.Option(".", help="Repository to run the det_tools slots in"),
    manifest: str = typer.Option(
        None, help="Seeded-defect manifest (yaml) — measures catch-rate and registers"
    ),
    baseline: float = typer.Option(
        1.0, help="Reference (python-lane) catch-rate the parity margin is measured against"
    ),
):
    """Run a language's det_tools slots (ADR-U16). Skipped slots are loud —
    a missing scanner is NOT clean. With --manifest, measures the
    seeded-defect catch-rate and registers the toolchain (or labels it
    PROVISIONAL with the lagging slots named)."""
    from ai_venture_studio.adoption import (
        benchmark_toolchain,
        load_seeded_manifest,
        register_toolchain,
        run_toolchain,
    )

    report = run_toolchain(repo_dir, language)
    table = Table(show_lines=False)
    for col in ("Slot", "Status", "Detail"):
        table.add_column(col)
    for r in report.results:
        color = {"clean": "green", "findings": "yellow"}.get(r.status, "red")
        table.add_row(r.slot, f"[{color}]{r.status}[/{color}]", r.detail)
    console.print(table)

    if manifest is None:
        if report.skipped_slots:
            console.print(
                f"[red]skipped: {', '.join(report.skipped_slots)} — "
                "install or override argv in .mas/toolchains.yaml[/red]"
            )
            raise typer.Exit(code=1)
        raise typer.Exit(code=0)

    result = benchmark_toolchain(report, load_seeded_manifest(manifest))
    record = register_toolchain(repo_dir, result, baseline_rate=baseline)
    color = "green" if record.status == "registered" else "yellow"
    console.print(
        f"[bold {color}]{record.status}[/bold {color}] — catch-rate "
        f"{record.catch_rate:.0%} (baseline {record.baseline_rate:.0%}, "
        f"margin {record.parity_margin:.0%})"
    )
    if record.gaps:
        console.print(f"lagging slots: {', '.join(record.gaps)}")
    if record.status == "provisional":
        raise typer.Exit(code=1)


@app.command()
def calibrate(
    language: str = typer.Argument(..., help="Language lane: python | java | dotnet"),
    repo_dir: str = typer.Option(
        None, help="Seeded lane dir (default: the bundled tests/toolchains/seeded/<lang>)"
    ),
    manifest: str = typer.Option(
        None, help="Manifest yaml (default: <lane>/seeded.yaml)"
    ),
):
    """Calibrate a language lane's manifest patterns against the real
    scanners (run inside `make calibrate`, where the binaries exist). Writes
    a per-defect report — caught/missed plus the actual slot output for each
    miss — so hand-labeled patterns can be fixed. A miss on a slot that ran
    means the PATTERN is wrong, not the scanner; a skipped slot means the
    binary is absent."""
    from ai_venture_studio.adoption import write_calibration_report
    from ai_venture_studio.adoption.calibrate import calibration_report

    seeded = Path(__file__).resolve().parent.parent.parent / "tests" / "toolchains" / "seeded"
    lane = Path(repo_dir) if repo_dir else seeded / language
    manifest_path = Path(manifest) if manifest else lane / "seeded.yaml"
    if not manifest_path.exists():
        console.print(f"[red]no manifest at {manifest_path}[/red]")
        raise typer.Exit(code=2)

    report = calibration_report(lane, language, manifest_path)
    # Write under CWD (the container mounts it), not the lane dir which is
    # ephemeral inside the image.
    out = write_calibration_report(lane, language, manifest_path, out_base=Path.cwd())

    color = "green" if not report.needs_recalibration and not report.skipped_slots else "yellow"
    console.print(
        f"[bold {color}]{language}[/bold {color}] catch-rate "
        f"{report.catch_rate:.0%} ({report.caught}/{report.total})"
    )
    if report.skipped_slots:
        console.print(
            f"[red]skipped slots (binary absent): {', '.join(report.skipped_slots)}[/red]"
        )
    if report.misses:
        table = Table(show_lines=False, title="misses — fix the pattern or the scanner rule")
        for col in ("Defect", "Slot", "Expected pattern", "Why missed"):
            table.add_column(col)
        for m in report.misses:
            table.add_row(m.defect_id, m.slot, m.expected_pattern, m.detail)
        console.print(table)
    console.print(f"Full report (with slot output for each miss): {out}")
    if report.needs_recalibration or report.skipped_slots:
        raise typer.Exit(code=1)


@app.command("eval-gate")
def eval_gate_cmd(
    scores: str = typer.Argument(..., help="YAML file of metric: value pairs"),
    repo_dir: str = typer.Option(".", help="Workspace with .mas/eval-baseline.yaml"),
    pin: bool = typer.Option(
        False, help="Pin these scores as the new baseline instead of gating "
        "(the file diff is the reviewable artifact — commit it via PR)"
    ),
    tolerance: float = typer.Option(0.01, help="Tolerance when pinning"),
):
    """Eval-set regression gate (§18.48.1): score deltas vs the pinned
    baseline. A pinned metric missing from the scores fails — unmeasured
    never reads as unregressed."""
    import yaml as yaml_lib

    from ai_venture_studio.adoption import eval_gate, pin_baseline

    data = yaml_lib.safe_load(Path(scores).read_text(encoding="utf-8")) or {}
    values = {str(k): float(v) for k, v in (data.get("metrics") or data).items()}
    if pin:
        path = pin_baseline(repo_dir, values, tolerance=tolerance)
        console.print(f"Baseline pinned: {path} — commit the diff via PR.")
        raise typer.Exit(code=0)
    result = eval_gate(repo_dir, values)
    table = Table(show_lines=False)
    for col in ("Metric", "Status", "Baseline", "Current", "Delta"):
        table.add_column(col)
    for v in result.verdicts:
        color = {"ok": "green", "unpinned": "yellow"}.get(v.status, "red")
        table.add_row(
            v.metric, f"[{color}]{v.status}[/{color}]",
            "" if v.baseline is None else f"{v.baseline}",
            "" if v.current is None else f"{v.current}",
            "" if v.delta is None else f"{v.delta:+}",
        )
    console.print(table)
    if not result.passed:
        raise typer.Exit(code=1)
    if result.unpinned:
        console.print(
            f"[yellow]unpinned metrics (pin to make them gate): "
            f"{', '.join(result.unpinned)}[/yellow]"
        )


@app.command()
def idempotency(
    run_a: str = typer.Argument(..., help="Output directory of the first run"),
    run_b: str = typer.Argument(..., help="Output directory of the re-run"),
):
    """Backfill idempotency check (§18.48.1): the fixture-slice re-run must
    be byte-identical. Two empty runs are an error, not a pass."""
    from ai_venture_studio.adoption import idempotency_check

    result = idempotency_check(run_a, run_b)
    if result.identical:
        console.print("[green]identical[/green] — backfill is idempotent on this slice")
        raise typer.Exit(code=0)
    for label, paths in (
        ("content differs", result.content_diffs),
        ("only in first", result.only_in_first),
        ("only in second", result.only_in_second),
    ):
        for p in paths:
            console.print(f"[red]{label}[/red]: {p}")
    raise typer.Exit(code=1)


@app.command("data-checks")
def data_checks(repo_dir: str = typer.Option(".", help="Workspace directory")):
    """Run the workspace's external data checks (dbt auto-detected;
    others declared in .mas/data-checks.yaml). Skipped is loud, never clean."""
    from ai_venture_studio.adoption import run_data_checks

    results = run_data_checks(repo_dir)
    table = Table(show_lines=False)
    for col in ("Check", "Status", "Detail"):
        table.add_column(col)
    for r in results:
        color = {"clean": "green", "findings": "yellow"}.get(r.status, "red")
        table.add_row(r.slot, f"[{color}]{r.status}[/{color}]", r.detail)
    console.print(table)
    if any(r.status in ("skipped", "error", "findings") for r in results):
        raise typer.Exit(code=1)


@app.command()
def dwell(repo_dir: str = typer.Option(".", help="Repository the reviews ran in")):
    """Approval-dwell-time report (F-18.3): how long humans actually sit on
    Gate-3 escalations before deciding. Median collapse + zero overrides
    flags the rubber-stamp pattern."""
    from ai_venture_studio.adoption import gate_dwell_report

    report = gate_dwell_report(repo_dir)
    for note in report.notes:
        style = "bold red" if report.rubber_stamp else "yellow"
        console.print(f"[{style}]{note}[/{style}]")
    if report.samples:
        console.print(
            f"{len(report.samples)} escalation(s) — median {report.median_s}s, "
            f"p90 {report.p90_s}s, override rate {report.override_rate:.0%}"
        )
        table = Table(show_lines=False)
        for col in ("Review", "Dwell (s)", "Decision"):
            table.add_column(col)
        for s in report.samples:
            table.add_row(s.review_id, f"{s.dwell_s:.0f}", s.decision)
        console.print(table)
    if report.rubber_stamp:
        raise typer.Exit(code=1)


@app.command()
def attest(
    review_id: str = typer.Argument(
        None, help="Review to chain into the ledger; omit to just verify"
    ),
    repo_dir: str = typer.Option(".", help="Repository the reviews ran in"),
):
    """Attestation ledger (§18.49): chain a review's gate/verdict records
    into the append-only hash-chained ledger, then verify the whole chain.
    Integrity only — org-key signing is a separate, deferred decision."""
    from ai_venture_studio.adoption import attest_review, verify_ledger

    if review_id is not None:
        try:
            count = attest_review(repo_dir, review_id)
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=2) from exc
        console.print(f"attested {count} record(s) from review {review_id}")

    verification = verify_ledger(repo_dir)
    if verification.ok:
        console.print(
            f"[green]chain verified[/green] — {verification.entries} entries"
        )
        raise typer.Exit(code=0)
    console.print(
        f"[bold red]LEDGER INTEGRITY FAILURE[/bold red] at seq "
        f"{verification.first_bad_seq}:"
    )
    for problem in verification.problems:
        console.print(f"  - {problem}")
    raise typer.Exit(code=1)


@app.command("cab-package")
def cab_package(
    review_id: str = typer.Argument(..., help="Review ID (directory under .mas/reviews/)"),
    repo_dir: str = typer.Option(".", help="Repository the review ran in"),
    change_id: str = typer.Option(None, help="CAB change record id (defaults to review id)"),
):
    """Assemble a CAB change package from a finished review: exports the
    evidence bundle, pre-fills what the audit trail knows, and runs the
    Gate-R preflight. Rollback plan and approver stay human — a fresh
    package is not eligible until a person completes it. Submission itself
    is always human."""
    from ai_venture_studio.adoption import (
        gate_r_entry,
        prepare_change_package,
        save_change_package,
    )

    try:
        package = prepare_change_package(repo_dir, review_id, change_id=change_id)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    path = save_change_package(repo_dir, package)
    entry = gate_r_entry(repo_dir, package)

    table = Table(show_lines=False)
    for col in ("Check", "Status", "Detail"):
        table.add_column(col)
    for r in entry.results:
        table.add_row(
            r.check.id,
            "[green]pass[/green]" if r.passed else "[red]fail[/red]",
            r.detail or r.check.description,
        )
    console.print(table)
    console.print(f"Package: {path}")
    if entry.eligible:
        console.print("[green]Gate R entry: eligible — a human submits.[/green]")
    else:
        console.print(
            "[yellow]Not yet eligible — complete the failing fields in the "
            "package file and re-run.[/yellow]"
        )
        raise typer.Exit(code=1)


@app.command("claim-lint")
def claim_lint_cmd(
    ledger: str = typer.Argument(..., help="Path to a claims/*.claim.yaml ledger"),
    kind: str = typer.Option(
        "market", help="Artifact kind: opportunity | market | prd | launch"
    ),
    mas_dir: str = typer.Option(
        ".mas", help="Workspace .mas directory (product-policy.yaml, evidence/)"
    ),
):
    """Deterministic claim-ledger lint (§20.53.3) — the outer loop's ears_lint.

    Exit 0 clean, 1 findings (JSONL on stdout), 2 malformed input."""
    import json

    from ai_venture_studio.product import lint_ledger, load_ledger, load_product_policy

    try:
        doc = load_ledger(ledger)
        policy = load_product_policy(mas_dir)
    except Exception as exc:  # malformed input is exit 2, not a stack trace
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    findings = lint_ledger(doc, kind, policy=policy)
    for finding in findings:
        print(json.dumps(finding.model_dump()))
    if findings:
        raise typer.Exit(code=1)


def _run_stage(spec, user_input: str, workspace: str, provider: str) -> None:
    """Run one product stage, persist the report, exit per outcome."""
    import yaml as _yaml
    from pathlib import Path as _Path

    from ai_venture_studio.product.stage_engine import run_product_stage

    try:
        report = run_product_stage(spec, user_input, workspace, provider=provider)
    except ValueError as exc:  # writer exhausted its revisions on the contract
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    report_path = _Path(workspace) / ".mas" / "product" / f"{spec.name}-report.yaml"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _yaml.safe_dump(report.model_dump(), sort_keys=False, allow_unicode=True)
    )
    console.print(f"[bold]{spec.name}[/bold]: {report.status} "
                  f"({len(report.voter_findings)} verified finding(s), "
                  f"{report.revisions} revision(s))")
    console.print(report.leader_summary)
    for path in report.artifacts:
        console.print(f"  wrote {path}")
    if report.status != "ok":
        for finding in report.det_findings:
            console.print(f"  [red]{finding.get('rule')}[/red]: {finding.get('message')}")
        for key, value in report.gate.items():
            if key != "passed":
                console.print(f"  gate.{key}: {value}")
        raise typer.Exit(code=1)


@app.command("opportunity")
def opportunity_cmd(
    signals: str = typer.Argument(..., help="YAML list of raw signals "
                                            "({id, source_id, text, locator})"),
    workspace: str = typer.Option(".", help="Product workspace"),
    provider: str = typer.Option("anthropic", help="LLM provider (mock for offline)"),
):
    """P0 Opportunity Sensing (§20.54): cluster real signals, draft >=3
    candidates, det-tools + five voters + verify + leader, Gate PL0."""
    import yaml as _yaml
    from pathlib import Path as _Path

    from ai_venture_studio.product import RawSignal, cluster_signals
    from ai_venture_studio.product.sources import SignalSourceError, load_signal_sources
    from ai_venture_studio.product.stages import opportunity_spec

    try:
        raw = _yaml.safe_load(_Path(signals).read_text()) or []
        parsed = [RawSignal(**s) for s in raw]
        declared = {s.id for s in load_signal_sources(_Path(workspace) / ".mas")}
        undeclared = sorted({s.source_id for s in parsed} - declared)
        if undeclared:
            raise SignalSourceError(
                f"signal sources {undeclared} not declared in "
                ".mas/signal-sources.yaml — no standing, no source (§20.54.2)"
            )
    except (SignalSourceError, ValueError, OSError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    clusters = cluster_signals(parsed)
    # The writer must cite the signals' own locators verbatim — so the
    # signals travel with their locators, not just cluster membership
    # (found by the first real-provider smoke: a locator the prompt never
    # contained cannot be cited, and the standing check rightly blocked).
    user_input = _yaml.safe_dump(
        {"clusters": [c.model_dump() for c in clusters],
         "signals": [s.model_dump() for s in parsed]},
        sort_keys=False, allow_unicode=True,
    )
    _run_stage(opportunity_spec(workspace), user_input, workspace, provider)


@app.command("probe")
def probe_cmd(
    url: str = typer.Argument(..., help="https URL of one public page"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    method: str = typer.Option("competitor_probe", help="Evidence method tag"),
    out: str = typer.Option(
        "", help="Append the evidence entry to this YAML file "
                 "(default: print it for you to paste into --evidence)"
    ),
):
    """Fetch one public page and record it as a probe (quarantined).

    The bytes are snapshotted to .mas/evidence/ and you get a hash + locator
    back — never the page content, which is what keeps a hostile page from
    reaching a privileged session. Only locators that a source declared in
    .mas/signal-sources.yaml already has standing for can be probed, and the
    fetch is yours: no agent can call this.
    """
    from pathlib import Path as _Path

    import yaml

    from ai_venture_studio.product.market import ProbeFetchError, fetch_probe
    from ai_venture_studio.product.sources import (
        SignalSourceError,
        load_signal_sources,
    )

    mas_dir = _Path(repo_dir).resolve() / ".mas"
    try:
        sources = load_signal_sources(mas_dir)
        entry, findings = fetch_probe(
            url, sources=sources, mas_dir=mas_dir, method=method
        )
    except (ProbeFetchError, SignalSourceError, ValueError, OSError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    for finding in findings:
        console.print(f"[yellow]{finding.rule}: {finding.message}[/yellow]")
    payload = {"evidence": [entry]}
    if out:
        path = _Path(out)
        existing = yaml.safe_load(path.read_text()) if path.exists() else None
        merged = (existing or {}).get("evidence", []) + [entry]
        path.write_text(
            yaml.safe_dump({"evidence": merged}, sort_keys=False,
                           allow_unicode=True),
            encoding="utf-8",
        )
        console.print(f"appended to {path} ({len(merged)} probe(s))")
    else:
        console.print(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
    if findings:
        # Contaminated evidence is usable only with the flag attached, so the
        # exit code says "read this before citing it" rather than "failed".
        raise typer.Exit(code=3)


@app.command("market")
def market_cmd(
    candidate: str = typer.Argument(..., help="Candidate id or statement from "
                                              "product/opportunities.md"),
    workspace: str = typer.Option(".", help="Product workspace"),
    provider: str = typer.Option("anthropic"),
    disconfirmation_answered: bool = typer.Option(
        False, help="Set once every Disconfirmation finding has an evidence answer"),
    regulatory_triaged: bool = typer.Option(
        False, help="Set once regulatory findings are triaged"),
    evidence: str = typer.Option(
        None, help="YAML of recorded evidence the writer may cite: probe "
                   "entries from record_probe (with artifact hashes) and "
                   "owned crm://analytics figures (§20.55.3)"),
):
    """P1 Market & Viability (§20.55): bottom-up sizing, probe-derived
    facts, six voters incl. Disconfirmation, deterministic Gate PL1 entry.
    The decision itself is `market-approve`."""
    from pathlib import Path as _Path

    from ai_venture_studio.product.stages import market_spec

    context = ""
    opportunities = _Path(workspace) / "product" / "opportunities.md"
    if opportunities.exists():
        context = f"\n\n<opportunities>\n{opportunities.read_text()}\n</opportunities>"
    if evidence:
        context += (
            "\n\n<recorded_evidence>\n"
            + _Path(evidence).read_text()
            + "\n</recorded_evidence>\n"
            "Cite ONLY the recorded evidence above (verbatim locators and "
            "artifact hashes) plus clearly-labeled model_inference within the "
            "ratio ceiling. Never invent a locator."
        )
    _run_stage(
        market_spec(workspace,
                    disconfirmation_answered=disconfirmation_answered,
                    regulatory_triaged=regulatory_triaged),
        f"<candidate>\n{candidate}\n</candidate>{context}",
        workspace, provider,
    )


@app.command("market-approve")
def market_approve_cmd(
    outcome: str = typer.Option(..., help="pursue | test_first | park | reject"),
    decider: str = typer.Option(..., help="The named human deciding"),
    scope_tier: str = typer.Option("", help="Required for pursue"),
    named_test: str = typer.Option("", help="Required for test_first"),
    park_reason: str = typer.Option("", help="Required for park"),
    workspace: str = typer.Option("."),
):
    """Record the human Gate PL1 decision (§20.55.5). forbidden_autonomous:
    this gate, always."""
    import yaml as _yaml
    from pathlib import Path as _Path

    from ai_venture_studio.product import GatePL1Decision

    try:
        decision = GatePL1Decision(
            outcome=outcome, decider=decider, scope_tier=scope_tier,
            named_test=named_test, park_reason=park_reason,
        )
        decision.validate_completeness()
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    path = _Path(workspace) / ".mas" / "product" / "gate-pl1.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_yaml.safe_dump(decision.model_dump(), sort_keys=False))
    console.print(f"[green]Gate PL1 recorded[/green]: {outcome} by {decider}")


@app.command("prd")
def prd_cmd(
    workspace: str = typer.Option(".", help="Product workspace"),
    provider: str = typer.Option("anthropic"),
    metrics_dir: str = typer.Option(None, help="Metric vocabulary directory "
                                               "(default: <workspace>/metrics)"),
):
    """P2 Product Definition (§20.56): the PRD with outcomes, non-goals,
    kill criteria; prd_lint deterministic; five voters. Approval + handoff
    is `prd-approve`."""
    from pathlib import Path as _Path

    from ai_venture_studio.product.stages import prd_spec

    parts = []
    for rel in ("market/market.md", "product/opportunities.md"):
        path = _Path(workspace) / rel
        if path.exists():
            parts.append(f"<{path.stem}>\n{path.read_text()}\n</{path.stem}>")
    ledger = _Path(workspace) / "claims" / "market.claim.yaml"
    if ledger.exists():
        parts.append(f"<market_claims>\n{ledger.read_text()}\n</market_claims>")
    _run_stage(
        prd_spec(workspace, metrics_dir=metrics_dir),
        "\n\n".join(parts) or "No upstream artifacts found — state that and stop.",
        workspace, provider,
    )


@app.command("prd-approve")
def prd_approve_cmd(
    decider: str = typer.Option(..., help="The named human at Gate PL2"),
    workspace: str = typer.Option("."),
):
    """Record Gate PL2 (§20.56.4) and emit the machine-checked
    p2_to_stage1.yaml handoff. Cheap on purpose — the expensive judgment
    was Gate PL1's."""
    import yaml as _yaml
    from pathlib import Path as _Path

    from ai_venture_studio.product import (
        PRD,
        GatePL2Decision,
        emit_handoff,
        validate_handoff_at_dor,
        write_handoff,
    )

    root = _Path(workspace)
    try:
        prd_raw = _yaml.safe_load((root / "product" / "prd.yaml").read_text())
        prd = PRD(**prd_raw["prd"])
        prose = (root / "product" / "prd.md").read_text()
        decision = GatePL2Decision(
            acknowledged_kill_criteria=True, scope_tier=prd.scope_tier,
            decider=decider,
        )
    except (OSError, KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    handoff = emit_handoff(
        prd, prose, claim_ledger_ref="claims/prd.claim.yaml",
        outcomes_ref="product/outcomes.yaml",
    )
    path = write_handoff(handoff, root / "handoff" / "p2_to_stage1.yaml")
    validate_handoff_at_dor(path, prd_document_text=prose)  # prove it lands
    gate = root / ".mas" / "product" / "gate-pl2.yaml"
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_text(_yaml.safe_dump(decision.model_dump(), sort_keys=False))
    console.print(f"[green]Gate PL2 recorded[/green]; handoff at {path} "
                  "(validated at Discovery's DoR)")


@app.command("evidence")
def evidence_cmd(
    events: str = typer.Argument(..., help="YAML list of analytics events"),
    metric: str = typer.Option("activation_rate", help="Vocabulary metric to read"),
    cohort_field: str = typer.Option("signup_week"),
    cohort_start: str = typer.Option(..., help="ISO date the cohort window opened"),
    workspace: str = typer.Option("."),
    provider: str = typer.Option("anthropic"),
    metrics_dir: str = typer.Option(None, help="Default: <workspace>/metrics"),
):
    """P4 Product Evidence (§22.62): deterministic cohort reading through
    the privacy boundary FIRST, then the writer narrates and assigns
    verdicts against pre-stated falsifiers; Gate PL4."""
    import datetime as _dt
    import yaml as _yaml
    from pathlib import Path as _Path

    from ai_venture_studio.evidence import AnalyticsStore, cohort_calc, load_metric_vocabulary
    from ai_venture_studio.product import PRD
    from ai_venture_studio.product.stages import evidence_spec

    root = _Path(workspace)
    try:
        rows = _yaml.safe_load(_Path(events).read_text()) or []
        vocabulary = load_metric_vocabulary(metrics_dir or root / "metrics")
        definition = vocabulary[metric]
        prd = PRD(**_yaml.safe_load((root / "product" / "prd.yaml").read_text())["prd"])
        readings_list = cohort_calc(
            AnalyticsStore(rows), definition,
            cohort_field=cohort_field,
            cohort_start=_dt.date.fromisoformat(cohort_start),
            today=_dt.date.today(),
        )
    except (OSError, KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    reading = readings_list[0] if readings_list else None
    readings = {
        o.id: reading for o in prd.outcomes if o.metric == metric and reading
    }
    user_input = _yaml.safe_dump(
        {"outcomes": [o.model_dump() for o in prd.outcomes],
         "hypotheses": [h.model_dump() for h in prd.demand_hypotheses],
         "cohort_readings": {k: v.model_dump() for k, v in readings.items()}},
        sort_keys=False, allow_unicode=True,
    )
    _run_stage(
        evidence_spec(workspace, prd_outcome_ids=[o.id for o in prd.outcomes],
                      readings=readings),
        user_input, workspace, provider,
    )


@app.command("sweep")
def sweep_cmd(
    workspace: str = typer.Option(".", help="Workspace directory"),
    today: str = typer.Option(None, help="ISO date override (default: today)"),
):
    """The Sweep role (doc 29): harvest the maintenance queues the ledgers
    already keep, patch only what the rung + allowlist + contract permit,
    report the rest. SW0 (default) is report-only; a clean pass is
    recorded, never silent."""
    import datetime as _dt
    from pathlib import Path as _Path

    from ai_venture_studio.lanes.delivery import flag_lint
    from ai_venture_studio.sweep import (
        SweepConfigError,
        harvest_queues,
        load_sweep_config,
        run_sweep_pass,
    )

    root = _Path(workspace)
    day = _dt.date.fromisoformat(today) if today else _dt.date.today()
    try:
        config = load_sweep_config(root / ".mas")
    except SweepConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    flags_file = root / ".mas" / "flags.yaml"
    flag_issues = flag_lint(flags_file.read_text(), {}, today=day) if flags_file.exists() else []
    contributing = root / "CONTRIBUTING.md"
    chores = harvest_queues(
        root, today=day, flag_issues=flag_issues,
        contributing_text=contributing.read_text() if contributing.exists() else "",
    )
    digest = run_sweep_pass(root, chores, config=config, at=day.isoformat())
    console.print(f"[bold]sweep[/bold] {digest.rung}: {digest.items_inspected} "
                  f"inspected · {len(digest.actionable)} actionable · "
                  f"{len(digest.reported)} reported · "
                  f"action rate {digest.action_rate:.0%}")
    if digest.clean_pass:
        console.print(f"[green]clean pass[/green] recorded "
                      f"({digest.snapshot_hash[:18]}…)")
    for chore in digest.chores[:10]:
        marker = "→ PATCH" if chore in digest.actionable else "  report"
        console.print(f"  {marker}  [{chore.queue}] {chore.item}: {chore.detail[:70]}")


@app.command("telemetry")
def telemetry_cmd(
    action: str = typer.Argument(..., help="on | off | show"),
    workspace: str = typer.Option(".", help="Workspace directory"),
):
    """Opt-in usage telemetry (ADR-U28): default off, aggregate-only,
    schema-pinned. `show` prints the exact payload — never FDR content,
    code, prompts, outputs, repo names, or claim text. No endpoint is
    configured in this version: nothing is ever sent."""
    from ai_venture_studio.usage_telemetry import (
        render_payload,
        set_telemetry,
        telemetry_enabled,
    )

    if action == "show":
        print(render_payload(workspace))
        state = "on" if telemetry_enabled(workspace) else "off (default)"
        console.print(f"[dim]telemetry is {state}; no endpoint is configured — "
                      "nothing is sent either way[/dim]")
    elif action in ("on", "off"):
        set_telemetry(workspace, action == "on")
        console.print(f"telemetry {action} — inspect the exact payload any time "
                      "with `avs telemetry show`")
    else:
        console.print("[red]action must be on | off | show[/red]")
        raise typer.Exit(code=2)


@app.command("voter-gate")
def voter_gate_cmd(
    stage: str = typer.Argument(..., help="opportunity | market | prd | evidence | prioritization"),
    voter: str = typer.Option(None, help="One voter; default: every voter in the stage"),
    workspace: str = typer.Option("."),
    provider: str = typer.Option("anthropic", help="A REAL provider — judging an "
                                                   "LLM voter takes an LLM"),
):
    """Run the voter fixture gate (§11.19): 8 fixtures, >=87.5% to register.
    Results land in .mas/voter-registry.yaml; a failed voter stops voting."""
    from pathlib import Path as _Path

    from ai_venture_studio.product.stage_engine import load_voter_charters
    from ai_venture_studio.product.voter_gate import (
        VoterFixtureError,
        family_roots,
        record_gate_run,
        run_voter_gate,
    )

    skills_root, fixtures_root = family_roots(stage)
    charters = [
        (name, system)
        for name, system in load_voter_charters(stage, skills_root)
        if voter is None or name == voter
    ]
    if not charters:
        console.print(f"[red]no charter named {voter!r} in stage {stage!r}[/red]")
        raise typer.Exit(code=2)
    failed_any = False
    for name, system in charters:
        try:
            run = run_voter_gate(stage, name, system, provider=provider,
                                 fixtures_root=fixtures_root)
        except VoterFixtureError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=2) from exc
        record_gate_run(_Path(workspace) / ".mas", run)
        color = "green" if run.status == "registered" else "red"
        console.print(f"[{color}]{stage}/{name}: {run.status}[/{color}] "
                      f"({run.passed}/{run.total})")
        for result in run.results:
            if not result.passed:
                console.print(f"    [red]{result.label}[/red]: {result.detail}")
        failed_any = failed_any or run.status != "registered"
    if failed_any:
        raise typer.Exit(code=1)


@app.command("automerge")
def automerge_cmd(
    review_id: str = typer.Argument(..., help="A finished review's id"),
    repo_dir: str = typer.Option(".", help="Repository the review ran in"),
    method: str = typer.Option("squash", help="squash | merge | rebase"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Evaluate, never act"),
):
    """Merge a reviewed PR — only if an armed .mas/automerge-policy.yaml says
    every condition holds (ADR-031). Disarmed by default; refusals are
    logged with their reasons."""
    from pathlib import Path as _Path

    import yaml as _yaml

    from ai_venture_studio import automation, github

    finals = sorted(
        (_Path(repo_dir) / ".mas" / "reviews" / review_id).glob("[0-9]*-final.yaml")
    )
    if not finals:
        console.print(f"[red]no finished review {review_id!r}[/red]")
        raise typer.Exit(code=2)
    final = _yaml.safe_load(finals[-1].read_text(encoding="utf-8")) or {}
    target = str(final.get("target", ""))
    verdict = str(final.get("verdict", ""))
    test_report = final.get("test_report") or {}
    branch = github.pr_head_branch(target) or ""

    try:
        decision = automation.evaluate_merge(
            repo_dir,
            verdict=verdict,
            branch=branch,
            changed_files=list((final.get("diff") or {}).get("changed_files") or []),
            test_gate_status=test_report.get("status"),
            escalated=bool((final.get("hitl") or {}).get("issue_url")),
        )
    except automation.PolicyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    if not decision.allowed:
        automation.record(repo_dir, decision, detail=f"review {review_id}")
        console.print(f"[yellow]merge refused[/yellow] for review {review_id}:")
        for reason in decision.reasons:
            console.print(f"  · {reason}")
        raise typer.Exit(code=1)
    if dry_run:
        console.print(f"[green]merge would proceed[/green] ({target}, {method})")
        return
    ok, output = github.merge_pr(target, method=method)
    automation.record(
        repo_dir, decision,
        detail=f"review {review_id}: {'merged' if ok else 'gh failed'} {output[:200]}",
    )
    if not ok:
        console.print(f"[red]gh pr merge failed: {output[:200]}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]merged[/green] {target}")


@app.command("deploy-execute")
def deploy_execute_cmd(
    deploy_id: str = typer.Argument(..., help="A finished deploy review's id"),
    repo_dir: str = typer.Option(".", help="Repository the review ran in"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Evaluate, never act"),
):
    """Run the deploy command a human wrote in .mas/deploy-exec-policy.yaml,
    only on a PROMOTE with every condition met (ADR-031). The system never
    composes the command."""
    import subprocess as _sp
    from pathlib import Path as _Path

    import yaml as _yaml

    from ai_venture_studio import automation

    finals = sorted(
        (_Path(repo_dir) / ".mas" / "deploy-reviews" / deploy_id).glob("[0-9]*-final.yaml")
    )
    if not finals:
        console.print(f"[red]no finished deploy review {deploy_id!r}[/red]")
        raise typer.Exit(code=2)
    final = _yaml.safe_load(finals[-1].read_text(encoding="utf-8")) or {}

    try:
        policy = automation.load_policy(repo_dir, automation.DEPLOY_EXEC_POLICY)
        decision = automation.evaluate_deploy(
            repo_dir,
            verdict=str(final.get("verdict", "")),
            branch=str(final.get("branch", "")),  # never defaulted (ADR-031)
            changed_files=list(final.get("deploy_files") or []),
        )
    except automation.PolicyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    if not decision.allowed:
        automation.record(repo_dir, decision, detail=f"deploy-review {deploy_id}")
        console.print(f"[yellow]deploy not executed[/yellow] for {deploy_id}:")
        for reason in decision.reasons:
            console.print(f"  · {reason}")
        raise typer.Exit(code=1)
    console.print(f"[dim]$ {' '.join(policy.command)}[/dim]")
    if dry_run:
        console.print("[green]deploy would proceed[/green]")
        return
    proc = _sp.run(  # noqa: S603 — argv comes from the human-written policy
        policy.command, cwd=repo_dir, capture_output=True, text=True, timeout=1800
    )
    automation.record(
        repo_dir, decision,
        detail=f"deploy-review {deploy_id}: exit {proc.returncode} "
               f"{(proc.stdout or proc.stderr)[-200:]}",
    )
    console.print((proc.stdout or proc.stderr)[-2000:])
    if proc.returncode != 0:
        console.print(f"[red]deploy command exited {proc.returncode}[/red]")
        raise typer.Exit(code=1)
    console.print("[green]deploy command completed[/green]")


@app.command("tenant")
def tenant_cmd(
    action: str = typer.Argument(..., help="list | add"),
    tenant_id: str = typer.Argument(None, help="Tenant id (add)"),
    workspace: str = typer.Option(None, help="That tenant's workspace root (add)"),
    webhook_secret_ref: str = typer.Option(
        "", help="secret://ENV_NAME holding this tenant's GitHub webhook secret"
    ),
    repo_dir: str = typer.Option(".", help="Where .mas/tenants.yaml lives"),
):
    """Multi-tenant server registry (ADR-030). A tenant is a token and a
    workspace; workspaces must be disjoint and tokens are stored hashed."""
    from ai_venture_studio.tenants import TenantError, add_tenant, load_tenants

    try:
        tenants = load_tenants(repo_dir)
    except TenantError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    if action == "list":
        if not tenants:
            console.print("single-tenant mode (no .mas/tenants.yaml)")
            return
        table = Table(show_lines=False)
        for col in ("id", "workspace", "enabled", "webhook secret"):
            table.add_column(col)
        for tenant in tenants:
            table.add_row(
                tenant.id, tenant.workspace,
                "yes" if tenant.enabled else "no",
                tenant.webhook_secret_ref or "[dim](none)[/dim]",
            )
        console.print(table)
        return

    if action != "add":
        console.print("[red]action must be list | add[/red]")
        raise typer.Exit(code=2)
    if not tenant_id or not workspace:
        console.print("[red]add needs a tenant id and --workspace[/red]")
        raise typer.Exit(code=2)
    try:
        tenant, token = add_tenant(
            repo_dir, tenant_id, workspace, webhook_secret_ref=webhook_secret_ref
        )
    except TenantError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    console.print(f"[green]added tenant {tenant.id}[/green] → {tenant.workspace}")
    console.print(f"\n  token: [bold]{token}[/bold]\n")
    console.print("[yellow]This token is shown once and stored only as a hash — "
                  "save it now.[/yellow]")


@app.command("botfleet")
def botfleet_cmd(
    command: str = typer.Argument(..., help="The bot session command "
                                           "(emits the session protocol on stdout)"),
    repo_dir: str = typer.Option(".", help="Where to run sessions"),
    sessions: int = typer.Option(8, help="How many parallel sessions"),
    seed: int = typer.Option(1, help="Base seed; each session gets seed+i"),
    bounds: float = typer.Option(None, help="Play-area bound for out-of-bounds "
                                           "detection (±bounds per axis)"),
    net_profile: str = typer.Option("", help="Comma-separated netem profiles "
                                             "(wifi_poor,mobile_4g,intercontinental)"),
    workers: int = typer.Option(4, help="Concurrency"),
):
    """Bot playtests (doc 17 §45.2): run N sessions, triage crashes,
    softlocks, unreachable states and out-of-bounds positions, dedupe by
    signature, and print a reproduction command per finding.

    Finds crashes and stuck states — never whether the game is fun. That is
    the human playtest gate, which no bot replaces (§45.1)."""
    import shlex

    from ai_venture_studio.lanes.botfleet import run_fleet

    profiles = tuple(p.strip() for p in net_profile.split(",") if p.strip()) or None
    report = run_fleet(
        shlex.split(command), cwd=repo_dir, sessions=sessions, base_seed=seed,
        net_profiles=profiles, bounds=bounds, workers=workers,
    )
    color = {"ok": "green", "findings": "yellow", "skipped": "yellow"}.get(
        report.status, "red"
    )
    console.print(f"\n[bold {color}]{report.status}[/bold {color}] — {report.detail}")
    for finding in report.findings:
        console.print(f"\n  [yellow]{finding['kind']}[/yellow] "
                      f"({finding['sessions']} session(s)"
                      + (f", profiles: {', '.join(finding['net_profiles'])}"
                         if finding["net_profiles"] else "")
                      + f")\n    {finding['detail']}")
        console.print(f"    [dim]reproduce: {finding['reproduce']}[/dim]")
    if report.status == "findings":
        raise typer.Exit(code=1)
    if report.status == "error":
        raise typer.Exit(code=2)


@app.command("bench-criterion")
def bench_criterion_cmd(
    repo_dir: str = typer.Option(".", help="Repository holding benchmarks/results/"),
):
    """The capability kill criterion (PRD O-L2): has product-bench fallen
    below its floors for two consecutive runs? States, never decides — a
    fired criterion needs a recorded human decision at Gate PL5."""
    from ai_venture_studio.bench_criterion import evaluate

    state = evaluate(repo_dir)
    for run in state.runs_considered:
        console.print(f"  [dim]{run.summary()}[/dim]")
    color = "red" if state.fires else "green"
    console.print(f"[{color}]{state.detail}[/{color}]")
    if state.fires:
        console.print(
            "\n[bold]Gate PL5 requires YOUR recorded decision[/bold] — kill, "
            "pivot, or continue — in launch/gate-pl5-evaluation.yaml. Nothing "
            "here decides it."
        )
        raise typer.Exit(code=3)


@app.command("attention")
def attention_cmd(
    week: str = typer.Option(None, help="ISO year-week (default: last week)"),
    repo_dir: str = typer.Option(".", help="Repository holding metrics/attention-log.yaml"),
    confirm_hours: float = typer.Option(
        None, help="YOUR number for the week — logs the row (the machine never "
                   "sets this; the measured floor is only a floor)"
    ),
    by: str = typer.Option("", help="Who is confirming (required with --confirm-hours)"),
    note: str = typer.Option("", help="Anything the number needs said about it"),
):
    """Weekly maintenance attention: measure the observable floor from the
    ledgers, then log YOUR hours. This is the series the launch PRD's kill
    criterion is falsifiable by (doc 25 §76.4)."""
    import datetime as _dt

    from ai_venture_studio.attention import (
        AttentionError,
        LogRow,
        append_row,
        collect_floor,
        iso_week,
        streak_state,
    )

    target = week or iso_week(_dt.date.today() - _dt.timedelta(days=7))
    try:
        floor = collect_floor(repo_dir, target)
        state = streak_state(repo_dir)
    except AttentionError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    console.print(f"\n[bold]{floor.week}[/bold]  ({floor.window})")
    console.print(f"  {floor.summary()}")
    for item in floor.evidence[:10]:
        console.print(f"    [dim]{item.kind}: {item.locator} "
                      f"({item.seconds / 60:.0f}m)[/dim]")
    if len(floor.evidence) > 10:
        console.print(f"    [dim]… {len(floor.evidence) - 10} more[/dim]")
    console.print("\n[dim]The floor counts only timestamped acts. Reading a "
                  "review without touching a gate, thinking, and answering "
                  "questions all count toward attention and leave no "
                  "timestamp — so the logged number is yours, not this.[/dim]")

    if confirm_hours is None:
        console.print(f"\nkill criterion: {state.detail}")
        console.print(
            f"\nTo log it: [bold]avs attention --week {floor.week} "
            f"--confirm-hours <yours> --by <you>[/bold]"
        )
        return

    if not by.strip():
        console.print("[red]--by is required when logging: a number in this "
                      "series has an author[/red]")
        raise typer.Exit(code=2)
    row = LogRow(
        week=floor.week, window=floor.window, hours=float(confirm_hours),
        status="logged", decided_by=by.strip(), note=note.strip(),
        measured_floor_hours=floor.measured_floor_hours,
        evidence_count=len(floor.evidence),
    )
    try:
        path = append_row(repo_dir, row)
    except AttentionError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    console.print(f"[green]logged {row.hours}h for {row.week}[/green] → {path}")
    state = streak_state(repo_dir)
    color = "red" if state.fires else "yellow"
    console.print(f"[{color}]kill criterion: {state.detail}[/{color}]")
    if state.fires:
        console.print(
            "\n[bold]Gate PL5 now requires YOUR recorded decision[/bold] — "
            "kill, pivot, or continue — in launch/gate-pl5-evaluation.yaml "
            "(docs/v3-live-loop.md has the field). Nothing here decides it."
        )
        raise typer.Exit(code=3)


@app.command("loop")
def loop_cmd(
    root: str = typer.Option("launch", help="Cycle artifact directory "
                                           "(launch/ for this repo's own loop)"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable state"),
):
    """Where the live product loop stands, and what closes the v3.0.0 design
    gate. Reads the artifacts the stages already wrote; states, never
    decides — the gate needs a recorded human kill-or-pivot at PL5."""
    import json as _json

    from ai_venture_studio.product.cycle import read_cycle

    try:
        state = read_cycle(root)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    if json_out:
        console.print_json(_json.dumps(state.model_dump(mode="json")))
        raise typer.Exit(code=0)

    console.print(f"\n[bold]cycle[/bold] {state.root} · entry {state.entry_stage}")
    if state.entry_reason:
        console.print(f"[dim]{state.entry_reason.strip()}[/dim]")
    table = Table(show_lines=False)
    for col in ("", "stage", "artifacts"):
        table.add_column(col)
    for stage in state.stages:
        mark = "[green]✓[/green]" if stage.present else "[dim]·[/dim]"
        table.add_row(mark, f"{stage.id} {stage.label}",
                      ", ".join(stage.artifacts) or "[dim]none[/dim]")
    console.print(table)
    gates = Table(show_lines=False)
    for col in ("", "gate", "record"):
        gates.add_column(col)
    for gate in state.gates:
        mark = "[green]✓[/green]" if gate.present else "[dim]·[/dim]"
        gates.add_row(mark, f"{gate.id} {gate.label}",
                      ", ".join(gate.artifacts) or "[dim]none[/dim]")
    console.print(gates)
    console.print("[bold]v3.0.0 design gate[/bold]")
    for criterion in state.criteria:
        mark = "[green]met[/green]" if criterion.met else "[yellow]not yet[/yellow]"
        console.print(f"  {mark} {criterion.id}: {criterion.requirement}")
        console.print(f"        [dim]{criterion.detail}[/dim]")
    verdict = (
        "[bold green]design gate MET[/bold green]"
        if state.design_gate_met
        else "[bold yellow]design gate not met[/bold yellow]"
    )
    console.print(f"\n{verdict} — next: {state.next_action}")
    if state.pl5_requires_human_decision and state.pl5_decision is None:
        raise typer.Exit(code=3)  # a fired criterion is waiting on a human


@app.command("review-gate")
def review_gate_cmd(
    voter: str = typer.Option(None, help="One voter; default: all six"),
    workspace: str = typer.Option(".", help="Where .mas/voter-registry.yaml lives"),
    provider: str = typer.Option(None, help="Force one provider (e.g. 'mock')"),
):
    """Fixture-registration gate for the REVIEW voters (§11.19): 8 fixtures
    each, >=87.5% to register. A failed voter stops voting — `review` runs
    without it and says so."""
    from pathlib import Path as _Path

    from ai_venture_studio.product.voter_gate import VoterFixtureError, record_gate_run
    from ai_venture_studio.review_gate import review_voter_names, run_review_voter_gate

    names = [voter] if voter else review_voter_names()
    failed_any = False
    for name in names:
        try:
            run = run_review_voter_gate(
                name, provider_override=provider, repo_dir=workspace
            )
        except VoterFixtureError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=2) from exc
        record_gate_run(_Path(workspace) / ".mas", run)
        color = "green" if run.status == "registered" else "red"
        console.print(f"[{color}]review/{name}: {run.status}[/{color}] "
                      f"({run.passed}/{run.total})")
        for result in run.results:
            if not result.passed:
                console.print(f"    [red]{result.label}[/red]: {result.detail}")
        failed_any = failed_any or run.status != "registered"
    if failed_any:
        raise typer.Exit(code=1)


@app.command("prd-lint")
def prd_lint_cmd(
    prd_yaml: str = typer.Argument(..., help="PRD yaml (a 'prd:' mapping, §20.56.2)"),
    prose: str = typer.Option(..., help="Path to the prd.md prose document"),
    metrics_dir: str = typer.Option("metrics", help="Metric vocabulary directory"),
    ledger: str = typer.Option(None, help="claims/*.claim.yaml the PRD cites"),
):
    """PRD lint (§20.56): EARS/module leakage, non-goals, kill criteria,
    vocabulary metrics, instrumentation-or-task. Exit 0 clean / 1 findings
    (JSONL) / 2 malformed. Generated Planning tasks print to stderr."""
    import json
    import sys as _sys
    from pathlib import Path as _Path

    import yaml as _yaml

    from ai_venture_studio.evidence import load_metric_vocabulary
    from ai_venture_studio.product import PRD, load_ledger, prd_lint

    try:
        raw = _yaml.safe_load(_Path(prd_yaml).read_text())
        prd = PRD(**(raw.get("prd") or raw))
        prose_text = _Path(prose).read_text()
        claim_ids = set()
        if ledger:
            claim_ids = {
                str(c.get("id"))
                for c in load_ledger(ledger).get("claims") or []
                if isinstance(c, dict)
            }
        vocabulary = load_metric_vocabulary(metrics_dir)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    issues, tasks = prd_lint(
        prd, prose_text, vocabulary=vocabulary,
        ledger_claim_ids=claim_ids or set(prd.evidence_refs),
    )
    for issue in issues:
        print(json.dumps(issue.model_dump()))
    for task in tasks:
        print(f"PLANNING TASK: {task.title}", file=_sys.stderr)
    if issues:
        raise typer.Exit(code=1)


@app.command("handoff-check")
def handoff_check_cmd(
    handoff: str = typer.Argument(..., help="handoff/p2_to_stage1.yaml"),
    prd_document: str = typer.Option(..., help="The exact PRD document the handoff pins"),
):
    """Discovery's DoR check (§20.56.3): a malformed handoff fails here
    with a named error rather than being interpreted. Exit 0 / 2."""
    from pathlib import Path as _Path

    from ai_venture_studio.product import HandoffError, validate_handoff_at_dor

    try:
        accepted = validate_handoff_at_dor(
            handoff, prd_document_text=_Path(prd_document).read_text()
        )
    except (HandoffError, OSError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    console.print(
        f"[green]handoff ok[/green]: {accepted.prd_ref} "
        f"({len(accepted.hypothesis_seed)} hypothesis(es), "
        f"tier {accepted.scope_tier})"
    )


@app.command("experiment-check")
def experiment_check_cmd(
    design: str = typer.Argument(..., help="experiments/EXP-*.yaml"),
    weekly_traffic: int = typer.Option(..., help="Current eligible traffic per week"),
    max_days: int = typer.Option(60, help="Longest acceptable run window"),
):
    """Gate PL3-exp preflight (§21.61): schema, FDR plan, power, and the
    pre-registration pin if present. Exit 0 / 1 findings / 2 malformed."""
    import json
    from pathlib import Path as _Path

    from ai_venture_studio.experiment import (
        PreregistrationError,
        fdr_plan_check,
        load_design,
        power_calc,
        verify_at_analysis,
    )

    try:
        text = _Path(design).read_text()
        parsed = load_design(text)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    findings = [i.model_dump() for i in fdr_plan_check(parsed)]
    power_result = power_calc(
        baseline=parsed.power.baseline,
        mde_relative=parsed.power.mde_relative,
        arms=parsed.design_stage1.arms,
        weekly_traffic=weekly_traffic,
        max_days=max_days,
        alpha=parsed.power.alpha,
        power=parsed.power.power,
    )
    if power_result.status != "ok":
        findings.append({"rule": power_result.status, "message": power_result.detail})
    if parsed.preregistration_hash:
        try:
            verify_at_analysis(text, parsed.preregistration_hash)
        except PreregistrationError as exc:
            findings.append({"rule": "preregistration_mismatch", "message": str(exc)})
    for finding in findings:
        print(json.dumps(finding))
    if findings:
        raise typer.Exit(code=1)
    console.print(
        f"[green]design ok[/green]: n={power_result.n_per_arm}/arm, "
        f"~{power_result.expected_days} days"
    )


@app.command("preregister")
def preregister_cmd(
    design: str = typer.Argument(..., help="experiments/EXP-*.yaml to pin"),
):
    """Compute the pre-registration hash for a design (§21.61.3). Record it
    in the file's preregistration_hash field BEFORE any exposure — writing
    the pin in does not change the pin."""
    from pathlib import Path as _Path

    from ai_venture_studio.experiment import lock_preregistration

    print(lock_preregistration(_Path(design).read_text()))


@app.command("evidence-bundle")
def evidence_bundle(
    review_id: str = typer.Argument(..., help="Review ID (directory under .mas/reviews/)"),
    repo_dir: str = typer.Option(".", help="Repository the review ran in"),
):
    """Export the Gate-R evidence bundle (unsigned v0) for one review's
    audit trail — the artifact a human attaches to a CAB submission."""
    from ai_venture_studio.adoption import write_evidence_bundle

    try:
        path = write_evidence_bundle(repo_dir, review_id)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    console.print(f"Evidence bundle written: {path}")


def main() -> None:
    sys.exit(app())


if __name__ == "__main__":  # `python -m ai_venture_studio.cli` — the server's
    main()                  # detached workers run exactly this (PR #21 bug)
