"""`avs compound` calls a provider and never wrote what it spent.

The provider adapter buffers each call in process state; only a caller that
knows the workspace can flush it to `.mas/spend.jsonl`. The review graph,
build, autopilot and the Studio all do. The compounding loop did not — so
every run spent real money and left the ledger unchanged.

That was survivable while it was hand-run and occasional. It stopped being
survivable when `avs cadence` put it on a daily LaunchAgent: a standing,
recurring, unmetered cost. ADR-032 removed the spending *cap* and kept the
metering deliberately — this pins the kept half.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from ai_venture_studio import compound as comp
from ai_venture_studio import spend
from ai_venture_studio.cli import app


@pytest.fixture(autouse=True)
def _clean_buffer():
    with spend._lock:
        spend._buffer.clear()
    yield
    with spend._lock:
        spend._buffer.clear()


def _workspace(tmp_path):
    root = tmp_path / "ws"
    (root / ".mas").mkdir(parents=True)
    return root


def test_a_compounding_run_writes_what_it_spent(tmp_path, monkeypatch):
    root = _workspace(tmp_path)

    def _fake_propose(signals, *, provider, model):
        # Stand in for the provider adapter: a real call buffers its usage.
        spend.record("claude-sonnet-5", 4_000, 700)
        return []

    monkeypatch.setattr(comp, "propose", _fake_propose)

    result = CliRunner().invoke(app, ["compound", "--repo-dir", str(root)])
    assert result.exit_code == 0, result.output

    ledger = root / ".mas" / "spend.jsonl"
    assert ledger.exists(), "the compounding run spent and recorded nothing"
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["input_tokens"] == 4_000
    assert rows[0]["output_tokens"] == 700


def test_a_run_that_never_reached_a_provider_writes_no_ledger_noise(
    tmp_path, monkeypatch
):
    """An empty window short-circuits before any call. Flushing must not
    invent a row — a ledger that logs non-calls is as useless as one that
    misses calls."""
    root = _workspace(tmp_path)
    monkeypatch.setattr(comp, "propose", lambda signals, **kw: [])

    result = CliRunner().invoke(app, ["compound", "--repo-dir", str(root)])
    assert result.exit_code == 0, result.output

    ledger = root / ".mas" / "spend.jsonl"
    rows = (
        [line for line in ledger.read_text().splitlines() if line.strip()]
        if ledger.exists() else []
    )
    assert rows == []


def test_a_gepa_proposal_writes_what_the_optimizer_spent(tmp_path):
    """gepa has no production caller yet — no CLI command, no orchestrator
    wiring. That is exactly why the flush goes in now: `propose_charter`
    calls a provider and only `write_proposal` knows a workspace, so whoever
    wires it up later inherits the metering instead of the leak."""
    from ai_venture_studio import gepa

    root = _workspace(tmp_path)
    spend.record("claude-opus-4-8", 9_000, 1_200)

    proposal = gepa.GepaProposal(
        target="skills/security.md", baseline_holdout_rate=0.5,
        candidate_holdout_rate=0.7, improved=True, candidate_charter="body",
    )
    gepa.write_proposal(root, proposal, at="2026-08-06")

    rows = [
        json.loads(line)
        for line in (root / ".mas" / "spend.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert [(r["input_tokens"], r["output_tokens"]) for r in rows] == [(9_000, 1_200)]


def test_a_failing_smoke_still_records_what_the_calls_cost(tmp_path, monkeypatch):
    """`smoke` already flushed — nothing pinned it. The subtle path is the
    failing one: it exits 1 to block a release, and an early exit is exactly
    where a flush gets dropped by a later edit. The calls were made and paid
    for whether or not the boundary held."""
    from ai_venture_studio import smoke as smoke_mod

    root = _workspace(tmp_path)

    def _fake_run_smoke(providers, *, model=None):
        spend.record("claude-sonnet-5", 1_100, 90)
        return [
            smoke_mod.ProviderSmoke(
                provider="anthropic", model="claude-sonnet-5", status="failed",
                checks=[smoke_mod.Check(name="streams_large", status="failed")],
            )
        ]

    monkeypatch.setattr(smoke_mod, "run_smoke", _fake_run_smoke)

    result = CliRunner().invoke(app, ["smoke", "--repo-dir", str(root)])
    assert result.exit_code == 1, result.output

    rows = [
        json.loads(line)
        for line in (root / ".mas" / "spend.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert [(r["input_tokens"], r["output_tokens"]) for r in rows] == [(1_100, 90)]
