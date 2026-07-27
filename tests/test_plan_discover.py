import shutil

import pytest
import yaml

from autoproduct.upstream import (
    approve_brief,
    approve_plan,
    init_workspace,
    next_tasks,
    run_discovery,
    run_planning,
)
from autoproduct.upstream.plan import Task, dag_check

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)


class _RosterAwareStub:
    """Sequenced writer responses; the charter roster (voters, verifier,
    leader) answers by marker so stage tests don't have to count roster
    calls — the v0.32 roster port made that sequence charter-dependent."""

    def __init__(self, responses, seen=None):
        self._responses = responses
        self.seen = seen if seen is not None else []

    def complete(self, **kwargs):
        from autoproduct.product.stage_engine import (
            PRODUCT_LEADER_MARKER,
            PRODUCT_VERIFIER_MARKER,
            PRODUCT_VOTER_MARKER,
        )

        self.seen.append(kwargs)
        system = kwargs.get("system", "")
        if PRODUCT_VOTER_MARKER in system:
            return "findings: []"
        if PRODUCT_VERIFIER_MARKER in system:
            return "verdict: refuted\nreason: stub"
        if PRODUCT_LEADER_MARKER in system:
            return "summary: stub leader"
        return next(self._responses)


def _task(tid, deps=(), lane="api"):
    return Task(id=tid, title=tid, depends_on=list(deps), lane=lane, estimate_hours=2)


def test_dag_check_accepts_valid_dag():
    assert dag_check([_task("a"), _task("b", ["a"]), _task("c", ["a", "b"])]) == []


def test_dag_check_catches_cycle():
    issues = dag_check([_task("a", ["b"]), _task("b", ["a"])])
    assert any("cycle" in i for i in issues)


def test_dag_check_catches_unknown_and_duplicate():
    issues = dag_check([_task("b"), _task("b"), _task("c", ["ghost"])])
    text = " | ".join(issues)
    assert "unknown" in text and "duplicate" in text


def test_discovery_writes_brief_and_ledger(tmp_path):
    root = init_workspace(tmp_path / "p", "p", "web")
    brief = run_discovery(root, "a link sharing tool", provider="mock")
    assert brief.status == "proposed"
    assert {h.evidence for h in brief.hypotheses} <= {"measured", "sourced", "assumed"}
    ledger = yaml.safe_load((root / ".mas" / "hypotheses.yaml").read_text())
    assert len(ledger) == len(brief.hypotheses)
    assert all(e["verified"] is None for e in ledger)


def test_planning_requires_gate_u1(tmp_path):
    root = init_workspace(tmp_path / "p", "p", "web")
    run_discovery(root, "a link sharing tool", provider="mock")
    with pytest.raises(ValueError, match="Gate U1"):
        run_planning(root, provider="mock")


def test_planner_cycle_forces_revision(tmp_path):
    root = init_workspace(tmp_path / "p", "p", "web")
    run_discovery(root, "a link sharing tool, make a cycle", provider="mock")
    approve_brief(root)
    plan = run_planning(root, provider="mock")
    # Mock planner emits a t1<->t2 cycle on the first pass; dag_check
    # feedback forces the clean second pass.
    assert plan.revisions >= 1
    assert plan.status == "proposed"
    assert plan.dag_issues == []


def test_scope_lock_and_ready_queue(tmp_path):
    root = init_workspace(tmp_path / "p", "p", "web")
    run_discovery(root, "a link sharing tool", provider="mock")
    approve_brief(root)
    run_planning(root, provider="mock")
    locked = approve_plan(root)
    assert locked.status == "locked"
    ready = next_tasks(root)
    assert [t.id for t in ready] == ["t1"]  # only the task with no deps


def test_brief_writer_survives_a_bad_parse_streak(tmp_path, monkeypatch):
    """Unparseable writer output consumes a revision; the budget must
    survive a streak — run 4, case 02 died after only 2 attempts."""
    import autoproduct.upstream.discover as discover

    valid = (
        'title: "t"\nproblem: "p"\ntarget_user: "u"\n'
        'hypotheses:\n  - statement: "s"\n    evidence: "assumed"\n'
        'scope_now: ["a"]\nscope_later: []\nscope_never: []\n'
        'success_metrics: ["m"]\n'
    )
    responses = iter(["not: [valid", "still {bad", "nope: [", valid])

    monkeypatch.setattr(
        discover, "get_provider", lambda name: _RosterAwareStub(responses))
    root = init_workspace(tmp_path / "p", "p", "web")
    brief = discover.run_discovery(root, "an idea", provider="stub")
    assert brief.revisions == 3


def test_spec_writer_receives_the_literal_source_contract(tmp_path, monkeypatch):
    """The founder's FDR must reach the spec writer verbatim — run 5,
    case 04: the writer only saw the planner's paraphrase and re-invented
    field names ("direction" for "name") and enums (integer rounds for
    "day5"), so every probe 400'd against a fully built product."""
    import autoproduct.upstream.spec as spec_mod

    contract = 'POST /api/candidates {"name": 候选方向名} → {"id"}; round is "day5" or "day12"'
    seen = []
    responses = iter([
        'title: "t"\ndesign: |\n  d\ncriteria:\n  - "When a request arrives, '
        'the system shall respond."\ntest_skeletons:\n  - path: tests/test_a.py\n'
        '    purpose: "p"\n    covers: [0]\n',
    ])

    monkeypatch.setattr(
        spec_mod, "get_provider",
        lambda name: _RosterAwareStub(responses, seen))
    root = init_workspace(tmp_path / "p", "p", "web")
    spec_mod.run_spec_stage(root, "a task description", provider="stub",
                            source_contract=contract)
    writer_prompt = seen[0]["user"]
    assert "source_contract" in writer_prompt and '"day5"' in writer_prompt

    # Fallback: no explicit contract, but the workspace carries FDR.md.
    seen.clear()
    responses = iter([
        'title: "t2"\ndesign: |\n  d\ncriteria:\n  - "When a request arrives, '
        'the system shall respond."\ntest_skeletons:\n  - path: tests/test_b.py\n'
        '    purpose: "p"\n    covers: [0]\n',
    ])
    monkeypatch.setattr(
        spec_mod, "get_provider",
        lambda name: _RosterAwareStub(responses, seen))
    (root / "FDR.md").write_text(contract, encoding="utf-8")
    spec_mod.run_spec_stage(root, "another task", provider="stub")
    assert '"day5"' in seen[0]["user"]


def test_blocked_spec_records_why(tmp_path, monkeypatch):
    """A gap-blocked spec used to surface downstream as the useless
    'lint 0 issue(s)' (run 7 case 03 t2; live test t1) — the block reason
    must name the uncovered criteria."""
    import itertools

    import autoproduct.upstream.spec as spec_mod

    writer = (
        'title: "t"\ndesign: |\n  d\n'
        'criteria:\n'
        '  - "When a request arrives, the system shall respond."\n'
        '  - "When a bad request arrives, the system shall reject it."\n'
        'test_skeletons:\n  - path: tests/test_a.py\n    purpose: "p"\n    covers: [0]\n'
    )
    responses = itertools.cycle([writer])

    monkeypatch.setattr(
        spec_mod, "get_provider", lambda name: _RosterAwareStub(responses))
    root = init_workspace(tmp_path / "p", "p", "web")
    spec = spec_mod.run_spec_stage(root, "a task", provider="stub")
    assert spec.status == "blocked"
    assert any("covered by no test skeleton" in r and "1" in r for r in spec.block_reasons)
