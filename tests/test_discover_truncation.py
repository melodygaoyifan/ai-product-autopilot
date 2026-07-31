"""A cut-off brief must say it was cut off.

A 4.6KB Chinese FDR overflowed the brief writer's 4096-token output cap on
every attempt. The loop reported "not a parseable YAML mapping" and told the
model to fix its quoting — which changes nothing about running out of room —
so all four revisions failed identically and the founder got a spinner and
then "brief failed schema after 4 attempts".
"""
from __future__ import annotations

import pytest

from ai_venture_studio.providers import base as provider_base
from ai_venture_studio.upstream import discover, init_workspace


class _Truncating:
    """A provider whose answers always stop at the output cap."""

    def __init__(self):
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        provider_base.record_stop_reason("max_tokens")
        return 'title: "a brief that got cut off mid'


def test_a_truncated_brief_is_reported_as_truncated(tmp_path, monkeypatch):
    root = init_workspace(tmp_path / "trunc", "trunc", "web")
    fake = _Truncating()
    monkeypatch.setattr(discover, "get_provider", lambda name: fake)

    with pytest.raises(ValueError) as caught:
        discover.run_discovery(root, "a very dense idea", provider="anthropic")

    detail = str(caught.value)
    assert "CUT OFF" in detail, detail
    assert "parseable YAML" not in detail, (
        "a size problem was reported as a syntax problem again"
    )


def test_the_writer_gets_room_for_a_dense_brief():
    """The cap that caused it. Guards the regression, cheaply."""
    import inspect

    source = inspect.getsource(discover.run_discovery)
    assert "max_tokens=8192" in source
    assert "max_tokens=4096" not in source


class _Scripted:
    """A writer whose answers are supplied in order, then a critic that
    always finds a major so the loop keeps revising."""

    GOOD = (
        'title: "A brief"\nproblem: "p"\ntarget_user: "u"\n'
        'hypotheses:\n  - statement: "s"\n    evidence: assumed\n'
        'scope_now: ["one"]\nscope_later: []\nscope_never: []\n'
        'success_metrics: ["m"]\n'
    )

    def __init__(self, script):
        self.script = list(script)
        self.seen = 0

    def complete(self, **kwargs):
        system = kwargs.get("system", "")
        if "PRODUCT-STAGE" in system or "VERIFIER" in system or "LEADER" in system:
            # critic seats: one verified major, so a revision is demanded
            if "VERIFIER" in system:
                return "verdict: verified\nreason: r"
            if "LEADER" in system:
                return "summary: s"
            return 'findings:\n  - severity: major\n    problem: "too big"\n    evidence: "one"'
        out = self.script[min(self.seen, len(self.script) - 1)]
        self.seen += 1
        # The real adapter records a stop reason on every call; a fake that
        # does not lets the previous test's "max_tokens" leak into this one.
        provider_base.record_stop_reason("end_turn")
        return out


def test_a_good_brief_survives_a_later_unparseable_revision(tmp_path, monkeypatch):
    """Observed live: attempt 3 parsed and was critiqued, attempt 4 came back
    malformed, and the run died — discarding a usable brief."""
    root = init_workspace(tmp_path / "keep", "keep", "web")
    writer = _Scripted([_Scripted.GOOD, "not yaml at all: [", "still not yaml: ["])
    monkeypatch.setattr(discover, "get_provider", lambda name: writer)

    brief = discover.run_discovery(root, "an idea", provider="anthropic")

    assert brief.title == "A brief"
    problems = " ".join(c.get("problem", "") for c in brief.critic_issues)
    assert "unparseable" in problems, "the discarded revision must be visible"


def test_it_still_raises_when_nothing_ever_parsed(tmp_path, monkeypatch):
    root = init_workspace(tmp_path / "none", "none", "web")
    writer = _Scripted(["not yaml: ["])
    monkeypatch.setattr(discover, "get_provider", lambda name: writer)

    with pytest.raises(ValueError, match="failed schema"):
        discover.run_discovery(root, "an idea", provider="anthropic")
