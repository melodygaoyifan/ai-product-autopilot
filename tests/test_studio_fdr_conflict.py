"""The FDR form must not silently overwrite a newer FDR.md.

Found in the wild: the founder's five answered clarify questions were
written into FDR.md while their browser tab still held the pre-answer
document. Clicking "check and plan" POSTed the stale textarea, the answers
were gone, and the assessor — seeing no answers — asked the same five
questions again. The founder saw "it keeps asking me"; the cause was a lost
update in this handler.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_venture_studio.studio import create_studio_app
from ai_venture_studio.upstream import init_workspace

STALE = "# FDR\n\nthe version the tab was rendered with\n"
NEWER = "# FDR\n\nthe version with the answers added\n"


@pytest.fixture
def workspace(tmp_path):
    return init_workspace(tmp_path / "conflict", "conflict", "web")


@pytest.fixture
def client(workspace):
    return TestClient(create_studio_app(workspace, provider="mock"))


def _base_of(client) -> str:
    """The fingerprint the current home page renders into its form."""
    import re

    page = client.get("/").text
    found = re.search(r"name=base value='([0-9a-f]+)'", page)
    assert found, "the FDR form no longer carries a base fingerprint"
    return found.group(1)


def test_a_stale_submit_does_not_destroy_newer_answers(client, workspace):
    (workspace / "FDR.md").write_text(STALE, encoding="utf-8")
    base = _base_of(client)
    # Something else updates the file — the CLI, another tab, an agent.
    (workspace / "FDR.md").write_text(NEWER, encoding="utf-8")

    page = client.post(
        "/fdr", data={"fdr": STALE, "base": base}, follow_redirects=True
    ).text

    assert (workspace / "FDR.md").read_text(encoding="utf-8") == NEWER
    assert "changed while you were editing" in page


def test_the_conflict_page_shows_both_versions(client, workspace):
    (workspace / "FDR.md").write_text(STALE, encoding="utf-8")
    base = _base_of(client)
    (workspace / "FDR.md").write_text(NEWER, encoding="utf-8")

    page = client.post(
        "/fdr", data={"fdr": STALE, "base": base}, follow_redirects=True
    ).text

    assert "the version the tab was rendered with" in page
    assert "the version with the answers added" in page


def test_the_founder_can_choose_their_own_version(client, workspace):
    """Overwriting is allowed — but only as an explicit choice."""
    (workspace / "FDR.md").write_text(STALE, encoding="utf-8")
    base = _base_of(client)
    (workspace / "FDR.md").write_text(NEWER, encoding="utf-8")
    client.post("/fdr", data={"fdr": STALE, "base": base}, follow_redirects=True)

    client.post(
        "/fdr", data={"fdr": STALE, "force": "1"}, follow_redirects=True
    )
    assert (workspace / "FDR.md").read_text(encoding="utf-8") == STALE


def test_an_unchanged_file_submits_normally(client, workspace):
    """The guard must be invisible in the ordinary case."""
    (workspace / "FDR.md").write_text(STALE, encoding="utf-8")
    base = _base_of(client)
    edited = STALE + "\nand a line the founder just typed\n"

    client.post("/fdr", data={"fdr": edited, "base": base}, follow_redirects=True)

    assert (workspace / "FDR.md").read_text(encoding="utf-8") == edited


def test_an_identical_resubmit_is_not_a_conflict(client, workspace):
    """Same bytes from both sides is not a lost update, whatever the hash
    says — refusing here would be a confusing dead end."""
    (workspace / "FDR.md").write_text(STALE, encoding="utf-8")
    client.post(
        "/fdr", data={"fdr": STALE, "base": "stale-fingerprint"},
        follow_redirects=True,
    )
    assert (workspace / "FDR.md").read_text(encoding="utf-8") == STALE


def test_the_form_carries_a_fingerprint_of_what_it_rendered(client, workspace):
    from ai_venture_studio.studio import _fdr_fingerprint

    (workspace / "FDR.md").write_text(STALE, encoding="utf-8")
    assert _base_of(client) == _fdr_fingerprint(STALE)
