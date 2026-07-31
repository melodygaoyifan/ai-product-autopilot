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
