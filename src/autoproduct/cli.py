"""CLI entry point: `autoproduct review <target>`.

Target is a GitHub PR URL (requires `gh` auth) or a local git revision
range such as `main...HEAD`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from autoproduct.adoption import StageInactiveError, check_stage
from autoproduct.orchestrator import is_interrupted, resume_review, run_review
from autoproduct.state import Verdict

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()

_DEFAULT_SKILLS = Path(__file__).resolve().parent.parent.parent / "skills"


@app.callback()
def _root() -> None:
    """autoproduct — multi-agent review-side SDLC system."""


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
        console.print("Run `autoproduct readiness` for the rung roadmap.")
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
            f"Resume with: autoproduct resume {state['review_id']} "
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
    from autoproduct.adoption import adoption_banners

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
):
    """Replay a past review's audit trail from its YAML mirror."""
    from autoproduct.replay import load_replay, summarize_step

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

    from autoproduct import compound as comp

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

    branch = f"autoproduct/compound-{date}"
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
            "--body", report + "\n\n🤖 opened by the autoproduct compounding loop",
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
    from autoproduct.bench import run_benchmark, save_result

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


_DEPLOY_SKILLS = Path(__file__).resolve().parent.parent.parent / "skills" / "deploy"


@app.command("deploy-review")
def deploy_review(
    target: str = typer.Argument(..., help="GitHub PR URL or git range"),
    repo_dir: str = typer.Option(".", help="Repository to review in"),
    skills_dir: str = typer.Option(str(_DEPLOY_SKILLS), help="Deploy voter skills"),
    provider: str = typer.Option(None, help="Force one provider (e.g. 'mock')"),
):
    """Gate 5 — Deployment Review MAS (§09.11). Recommends; never deploys."""
    from autoproduct.deploy import run_deploy_review

    try:
        activation = check_stage(repo_dir, "deploy_review")
    except StageInactiveError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("Run `autoproduct readiness` for the rung roadmap.")
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
    from autoproduct.maintenance import Incident, run_maintenance

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
        from autoproduct.maintenance.fixpr import generate_fix_pr

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
    from autoproduct.deploy import track_record

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
    from autoproduct.server import serve as run_server

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
    from autoproduct.jobqueue import worker_loop

    done = worker_loop(queue_db, repo_dir, max_jobs=max_jobs or None)
    console.print(f"worker exited after {done} job(s)")


@app.command()
def init(
    directory: str = typer.Argument(..., help="Workspace directory to create"),
    name: str = typer.Option(None, help="Project name (defaults to directory name)"),
    profile: str = typer.Option(..., help="Domain profile: web | miniprogram | app"),
):
    """Create a greenfield workspace: profile constraints, CLAUDE.md, specs/."""
    from autoproduct.upstream import init_workspace

    root = init_workspace(directory, name or Path(directory).name, profile)
    console.print(f"workspace ready: {root}")
    console.print(
        f"next: autoproduct spec \"<what you want to build>\" --repo-dir {root}"
    )


@app.command()
def spec(
    request: str = typer.Argument(..., help="What you want to build, in plain words"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider (e.g. 'mock')"),
):
    """Spec stage: EARS criteria + test skeletons, linted and critiqued."""
    from autoproduct.upstream import run_spec_stage

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
            f"Gate U3: autoproduct spec-approve {result.slug} --repo-dir {repo_dir}"
        )


@app.command("spec-approve")
def spec_approve(
    slug: str = typer.Argument(..., help="Spec slug"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
):
    """Gate U3 — human approval that makes a spec buildable."""
    from autoproduct.upstream import approve_spec

    result = approve_spec(repo_dir, slug)
    console.print(
        f"approved: {result.title}\n"
        f"next: autoproduct build {slug} --repo-dir {repo_dir}"
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
    from autoproduct.upstream import run_build

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
        console.print("\nhanding to review stage (autoproduct review HEAD~1)…")
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
    from autoproduct.upstream import run_discovery

    brief = run_discovery(repo_dir, idea, provider=provider)
    console.print(f"\n[bold]{brief.title}[/bold] — {brief.status}")
    for h in brief.hypotheses:
        console.print(f"  ({h.evidence}) {h.statement}")
    console.print(f"scope_now: {brief.scope_now}")
    console.print(f"brief: {Path(repo_dir) / 'product' / 'brief.md'}")
    console.print("Gate U1: autoproduct brief-approve")


@app.command("brief-approve")
def brief_approve(repo_dir: str = typer.Option(".", help="Workspace directory")):
    """Gate U1 — the human problem-selection decision."""
    from autoproduct.upstream import approve_brief

    brief = approve_brief(repo_dir)
    console.print(f"approved: {brief.title}\nnext: autoproduct plan")


@app.command()
def plan(
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider (e.g. 'mock')"),
):
    """Planning stage: task DAG from the approved brief (dag-checked)."""
    from autoproduct.upstream import run_planning

    result = run_planning(repo_dir, provider=provider)
    color = {"proposed": "green", "blocked": "red"}.get(result.status, "yellow")
    console.print(f"\n[bold {color}]{result.status}[/bold {color}] — {len(result.tasks)} task(s)")
    for t in result.tasks:
        deps = f" <- {','.join(t.depends_on)}" if t.depends_on else ""
        console.print(f"  {t.id} [{t.lane}] {t.title}{deps} ({t.estimate_hours}h)")
    if result.dag_issues:
        console.print(f"[red]dag issues: {result.dag_issues}[/red]")
    if result.status == "proposed":
        console.print("Gate U2 (scope lock): autoproduct plan-approve")


@app.command("plan-approve")
def plan_approve(repo_dir: str = typer.Option(".", help="Workspace directory")):
    """Gate U2 — lock scope; changes after this go through an SCR."""
    from autoproduct.upstream import approve_plan, next_tasks

    plan_result = approve_plan(repo_dir)
    ready = next_tasks(repo_dir)
    console.print(f"scope locked: {len(plan_result.tasks)} task(s)")
    for t in ready:
        console.print(f"  ready: {t.id} — autoproduct spec \"{t.description}\"")


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
    from autoproduct.upstream import init_workspace
    from autoproduct.upstream.autopilot import run_autopilot
    from autoproduct.upstream.fdr import write_template

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
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    port: int = typer.Option(8433, help="Port"),
    profile: str = typer.Option(None, help="Profile (only needed for a new workspace)"),
):
    """Founder Studio: the browser UI for the FDR flow (localhost only)."""
    from autoproduct.studio import serve_studio
    from autoproduct.upstream import init_workspace

    root = Path(repo_dir).resolve()
    if not (root / ".mas" / "project.yaml").exists():
        if not profile:
            console.print("[red]new workspace: pass --profile web|miniprogram|app[/red]")
            raise typer.Exit(code=2)
        init_workspace(root, root.name, profile)
    console.print(f"Studio: http://127.0.0.1:{port}  (workspace: {root})")
    serve_studio(root, port=port)


@app.command()
def preview(
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    port: int = typer.Option(8500, help="Port for the app"),
):
    """Run the built product locally so the founder can try it (web profile)."""
    import subprocess

    from autoproduct.upstream import load_project

    root = Path(repo_dir).resolve()
    project = load_project(root)
    if project.profile == "miniprogram":
        console.print(
            "小程序预览：用微信开发者工具打开这个目录即可（工具 → 导入项目）：\n"
            f"  {root}\n"
            "Open this directory in WeChat DevTools (import project) to preview."
        )
        return
    from autoproduct.upstream.provisioning import preview_env

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
    from autoproduct.upstream.autopilot import run_feature

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
    from autoproduct.upstream.spec import raise_scr

    path = raise_scr(repo_dir, slug, reason)
    console.print(f"raised: {path.name}\napprove with: autoproduct scr-approve {path.stem.split('-')[1]}")


@app.command("scr-approve")
def scr_approve(
    number: int = typer.Argument(..., help="SCR number"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
):
    """Approve an SCR — grants exactly one regeneration of the named spec."""
    from autoproduct.upstream.spec import approve_scr

    data = approve_scr(repo_dir, number)
    console.print(
        f"approved SCR-{number:03d} for spec {data['spec_slug']!r}: {data['reason']}\n"
        f"the next `autoproduct spec`/`add` touching it may now regenerate it once"
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
    from autoproduct.upstream.ship import push_web, ship as run_ship

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
    from autoproduct.product_bench import run_product_bench, save_summary

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
    """Continue reviews that crashed mid-run from their checkpoints."""
    from autoproduct.orchestrator import recover_reviews

    results = recover_reviews(repo_dir)
    if not results:
        console.print("nothing to recover")
        return
    for r in results:
        console.print(f"  {r['review_id']}: {r['status']}"
                      + (f" → {r.get('verdict')}" if r.get("verdict") else ""))


@app.command()
def correct(
    complaint: str = typer.Argument(..., help="What's wrong, in your own words"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider (e.g. 'mock')"),
):
    """M3 — 这不是我要的: repairs go through the fix path, scope changes
    raise an SCR (your complaint IS the approval, recorded verbatim)."""
    from autoproduct.upstream.correction import run_correction

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
    from autoproduct.upstream.walkthrough import generate_walkthrough

    console.print(f"written: {generate_walkthrough(repo_dir, provider=provider)}")


@app.command()
def digest(
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider"),
    days: int = typer.Option(7, help="Window"),
):
    """M5 — weekly plain-language digest from the product's own telemetry;
    reconciles the hypothesis ledger with observed events."""
    from autoproduct.upstream.telemetry import generate_digest

    console.print(f"written: {generate_digest(repo_dir, provider=provider, days=days)}")


@app.command("retry-task")
def retry_task(
    task_id: str = typer.Argument(..., help="Failed task id from the report"),
    repo_dir: str = typer.Option(".", help="Workspace directory"),
    provider: str = typer.Option("anthropic", help="Provider"),
):
    """M7 — retry ONE failed module without rebuilding anything else."""
    from autoproduct.upstream import approve_spec, run_build, run_spec_stage
    from autoproduct.upstream.plan import load_plan

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
    from autoproduct.upstream.autopilot import undo_last

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
    from autoproduct.upstream.probegen import verify_product

    path = verify_product(repo_dir, provider=provider)
    console.print(path.read_text(encoding="utf-8"))
    console.print(f"saved: {path}")


@app.command("setup-tests")
def setup_tests(repo_dir: str = typer.Option(".", help="Workspace directory")):
    """小程序: install jest + miniprogram-simulate so page-level tests run
    in the build/test gates (npm required)."""
    from autoproduct.upstream.ship import setup_miniprogram_tests

    result = setup_miniprogram_tests(repo_dir)
    color = {"ready": "green"}.get(result["status"], "yellow")
    console.print(f"[bold {color}]{result['status']}[/bold {color}] — {result['detail']}")


@app.command("services-cloud")
def services_cloud(repo_dir: str = typer.Option(".", help="Workspace directory")):
    """Attempt cloud AUTO-provisioning (Supabase CLI, gated on login);
    degrades to the guided SERVICES.md path when tooling is absent."""
    from autoproduct.upstream import load_project
    from autoproduct.upstream.provisioning import auto_provision_cloud, write_cloud_guide

    profile = load_project(repo_dir).profile
    write_cloud_guide(repo_dir, profile)
    result = auto_provision_cloud(repo_dir, profile)
    color = {"provisioned": "green"}.get(result["status"], "yellow")
    console.print(f"[bold {color}]{result['status']}[/bold {color}] — {result['detail']}")


@app.command()
def readiness(repo_dir: str = typer.Option(".", help="Workspace directory")):
    """Substrate readiness report (docs 18-19): active stages at the
    declared rung and what each missing rung would unlock."""
    from autoproduct.adoption import load_substrate_profile, readiness_report

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
    from autoproduct.adoption import (
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
    from autoproduct.adoption import write_calibration_report
    from autoproduct.adoption.calibrate import calibration_report

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

    from autoproduct.adoption import eval_gate, pin_baseline

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
    from autoproduct.adoption import idempotency_check

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
    from autoproduct.adoption import run_data_checks

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
    from autoproduct.adoption import gate_dwell_report

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
    from autoproduct.adoption import attest_review, verify_ledger

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
    from autoproduct.adoption import (
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

    from autoproduct.product import lint_ledger, load_ledger, load_product_policy

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

    from autoproduct.product.stage_engine import run_product_stage

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

    from autoproduct.product import RawSignal, cluster_signals
    from autoproduct.product.sources import SignalSourceError, load_signal_sources
    from autoproduct.product.stages import opportunity_spec

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

    from autoproduct.product.stages import market_spec

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

    from autoproduct.product import GatePL1Decision

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

    from autoproduct.product.stages import prd_spec

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

    from autoproduct.product import (
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

    from autoproduct.evidence import AnalyticsStore, cohort_calc, load_metric_vocabulary
    from autoproduct.product import PRD
    from autoproduct.product.stages import evidence_spec

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

    from autoproduct.product.stage_engine import load_voter_charters
    from autoproduct.product.voter_gate import (
        VoterFixtureError,
        record_gate_run,
        run_voter_gate,
    )

    charters = [
        (name, system)
        for name, system in load_voter_charters(stage)
        if voter is None or name == voter
    ]
    if not charters:
        console.print(f"[red]no charter named {voter!r} in stage {stage!r}[/red]")
        raise typer.Exit(code=2)
    failed_any = False
    for name, system in charters:
        try:
            run = run_voter_gate(stage, name, system, provider=provider)
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

    from autoproduct.evidence import load_metric_vocabulary
    from autoproduct.product import PRD, load_ledger, prd_lint

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

    from autoproduct.product import HandoffError, validate_handoff_at_dor

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

    from autoproduct.experiment import (
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

    from autoproduct.experiment import lock_preregistration

    print(lock_preregistration(_Path(design).read_text()))


@app.command("evidence-bundle")
def evidence_bundle(
    review_id: str = typer.Argument(..., help="Review ID (directory under .mas/reviews/)"),
    repo_dir: str = typer.Option(".", help="Repository the review ran in"),
):
    """Export the Gate-R evidence bundle (unsigned v0) for one review's
    audit trail — the artifact a human attaches to a CAB submission."""
    from autoproduct.adoption import write_evidence_bundle

    try:
        path = write_evidence_bundle(repo_dir, review_id)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    console.print(f"Evidence bundle written: {path}")


def main() -> None:
    sys.exit(app())


if __name__ == "__main__":  # `python -m autoproduct.cli` — the server's
    main()                  # detached workers run exactly this (PR #21 bug)
