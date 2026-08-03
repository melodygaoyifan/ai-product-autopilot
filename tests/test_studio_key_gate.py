"""The key gate: the tool is free, the model is not.

Before this, a founder who had never held an API key learned that fact as a
stack trace on their first send — the flow asked for a product description,
took it, and then died inside the provider adapter. The gate says whose
account pays BEFORE the first call, offers the one field that fixes it, and
names the doors (Bedrock, Vertex, Foundry, a mounted secret file) where
nothing is typed here at all.

Three states, and the secret handling that must hold in all of them: a
resolved key value never reaches rendered HTML, the failure log, or disk.
"""

from __future__ import annotations

import re
import shutil
from contextlib import contextmanager
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from ai_venture_studio.studio import (
    create_studio_app,
    provider_key_present,
    set_provider_key,
)
from ai_venture_studio.upstream import init_workspace

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)

#: Everything that could authenticate the anthropic adapter. Cleared so the
#: test sees what a founder with nothing sees, on a machine that has a key.
_KEY_ENV = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_FILE", "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_AUTH_TOKEN_FILE", "AVS_ANTHROPIC_MODE",
)

SECRET = "sk-ant-thisisthetestkeyvalue-0000"


@contextmanager
def _env(**overrides):
    """The environment minus every key variable, plus whatever this test
    wants set. Everything else stays — git needs its PATH."""
    import os

    base = {k: v for k, v in os.environ.items() if k not in _KEY_ENV}
    base.update({k: v for k, v in overrides.items() if v is not None})
    with mock.patch.dict(os.environ, base, clear=True):
        yield


def _studio(tmp_path, name="keys", provider="anthropic"):
    root = init_workspace(tmp_path / name, name, "web")
    return TestClient(
        create_studio_app(root, spawn=lambda r: 1, provider=provider)
    ), root


# ── state A: no key, and the provider is not the mock ────────────────────


def test_a_founder_with_no_key_is_told_whose_account_pays(tmp_path):
    with _env():
        client, _root = _studio(tmp_path)
        page = client.get("/").text

    assert "Connect the model first" in page
    assert "billed to your own provider account" in page
    assert "action=/key" in page          # the field that fixes it
    assert "<textarea" not in page        # …and NOT the describe state


def test_the_gate_stands_in_front_of_both_describe_doors(tmp_path):
    with _env():
        client, _root = _studio(tmp_path, "doors")
        for door in ("/", "/chat", "/?form=1"):
            assert "action=/key" in client.get(door).text, door


def test_the_gate_names_the_doors_that_need_no_key_typed_here(tmp_path):
    with _env():
        client, _root = _studio(tmp_path, "gateways")
        page = client.get("/").text

    for door in ("AVS_ANTHROPIC_MODE=bedrock", "AVS_ANTHROPIC_MODE=vertex",
                 "AVS_ANTHROPIC_MODE=foundry", "ANTHROPIC_API_KEY_FILE"):
        assert door in page, f"the gate does not name {door}"


def test_the_gate_offers_a_real_recorded_run_that_needs_no_key(tmp_path):
    """`avs replay --demo` in the browser: the vendored bundle rendered by
    the same timeline the workspace's own reviews use. A button that only
    LOOKED like a demo would be worse than no button."""
    with _env():
        client, _root = _studio(tmp_path, "demo")
        assert "href='/demo'" in client.get("/").text
        page = client.get("/demo").text

    assert "A recorded run" in page
    assert "avs replay --demo" in page
    assert "<table>" in page and "<tr>" in page   # the real steps
    assert "ESCALATE" in page or "APPROVE" in page  # the recorded verdict
    # It is a read of a shipped mirror, so there is nothing of this
    # workspace's own to attest.
    assert "/evidence" not in page


def test_a_gateway_mode_is_not_gated_at_all(tmp_path):
    """Bedrock/Vertex/Foundry authenticate through the cloud's own
    credentials. Asking those operators for a key would be asking for
    something that does not exist."""
    with _env(AVS_ANTHROPIC_MODE="bedrock"):
        assert provider_key_present("anthropic")
        client, _root = _studio(tmp_path, "bedrock")
        assert "action=/key" not in client.get("/").text


def test_the_cost_footer_states_no_figure_when_the_ledger_has_none(tmp_path):
    """A number on the page that asks for a payment method is the worst
    place in the product to guess one."""
    with _env():
        client, _root = _studio(tmp_path, "cost")
        page = client.get("/").text

    assert "Building is where the money goes" in page
    assert "no figure to show" in page
    assert not re.search(r"\$\d", page), "the gate invented a cost figure"


def test_the_cost_footer_uses_the_workspaces_own_ledger_when_it_has_one(tmp_path):
    from ai_venture_studio import spend

    with _env():
        client, root = _studio(tmp_path, "spent")
        # A figure needs a PRICE, not just a call. Without one this test used
        # to pass on "≥$0.00" — the misleading zero the building page showed
        # through a whole real build (see test_studio_spend_honesty.py).
        (root / ".mas").mkdir(exist_ok=True)
        (root / ".mas" / "cost-model.yaml").write_text(
            "prices:\n  claude-opus-4-8:\n    input: 5.0\n    output: 25.0\n",
            encoding="utf-8",
        )
        spend.record("claude-opus-4-8", 1_000_000, 0)
        spend.flush(root)
        page = client.get("/").text

    assert "spent" in page
    assert "$5.00" in page, "the ledger's own figure did not reach the footer"
    assert "no figure to show" not in page


# ── pasting a key: this process only ─────────────────────────────────────


def test_pasting_a_key_sets_it_for_this_process_only(tmp_path):
    import os

    with _env():
        client, root = _studio(tmp_path, "paste")
        assert "action=/key" in client.get("/").text
        client.post("/key", data={"key": SECRET}, follow_redirects=False)

        assert os.environ["ANTHROPIC_API_KEY"] == SECRET  # this process
        page = client.get("/").text
        assert "action=/key" not in page, "the gate did not stand down"
        assert "A key is set for this process" in page

    # …and nothing anywhere on disk holds it
    for path in root.rglob("*"):
        if path.is_file():
            assert SECRET not in path.read_text(encoding="utf-8", errors="ignore"), (
                f"the key was written to {path}"
            )


def test_the_page_says_in_those_words_that_nothing_is_written_to_disk(tmp_path):
    with _env():
        client, _root = _studio(tmp_path, "promise")
        page = client.get("/").text
    assert "never written to disk" in page


def test_a_resolved_key_never_appears_in_rendered_html(tmp_path):
    """The field is write-only: the page can ask for a key and can never
    show one back, not even the one it is already using."""
    with _env(ANTHROPIC_API_KEY=SECRET):
        client, _root = _studio(tmp_path, "noecho")
        pages = [client.get("/").text, client.get("/chat").text,
                 client.get("/?form=1").text, client.get("/live").text]
        client.post("/key", data={"key": SECRET})
        pages.append(client.get("/").text)

    for page in pages:
        assert SECRET not in page


def test_a_resolved_key_never_reaches_the_failure_log(tmp_path):
    """record_failure writes the exception and its traceback to
    .mas/studio-failures.jsonl. A provider that puts the key in its error
    message would leak it there — so the page that offers the paste box
    must never put one in an exception of its own."""
    import ai_venture_studio.upstream.autopilot as autopilot

    with _env(ANTHROPIC_API_KEY=SECRET):
        client, root = _studio(tmp_path, "logs", provider="mock")
        original = autopilot.run_autopilot

        def boom(*a, **k):
            raise RuntimeError("401 unauthorized: invalid x-api-key")

        autopilot.run_autopilot = boom
        try:
            client.post("/fdr", data={"fdr": "# a\nb\n"}, follow_redirects=True)
        finally:
            autopilot.run_autopilot = original

        log = (root / ".mas" / "studio-failures.jsonl").read_text(encoding="utf-8")

    assert "401 unauthorized" in log        # the failure IS recorded
    assert SECRET not in log                # the key is not


def test_an_empty_paste_changes_nothing_and_says_so(tmp_path):
    import os

    with _env():
        client, _root = _studio(tmp_path, "empty")
        page = client.post("/key", data={"key": "   "}, follow_redirects=True).text
        assert "not a usable key" in page
        assert "ANTHROPIC_API_KEY" not in os.environ


def test_the_mock_provider_is_never_gated_and_sets_nothing(tmp_path):
    """`--provider mock` bills nobody. Pressing the key route on a mock
    Studio (as the wireup gate does) must not put a key in the process."""
    import os

    with _env():
        client, _root = _studio(tmp_path, "mockws", provider="mock")
        assert "action=/key" not in client.get("/").text
        client.post("/key", data={"key": SECRET}, follow_redirects=True)
        assert "ANTHROPIC_API_KEY" not in os.environ


def test_set_provider_key_refuses_a_value_with_whitespace_in_it():
    """A paste that brought half a shell line with it is not a key."""
    import os

    with _env():
        assert set_provider_key("anthropic", "sk-ant export FOO=1") is None
        assert set_provider_key("anthropic", "") is None
        assert set_provider_key("mock", SECRET) is None
        assert "ANTHROPIC_API_KEY" not in os.environ
        assert set_provider_key("anthropic", f"  {SECRET}  ") == "ANTHROPIC_API_KEY"
        assert os.environ["ANTHROPIC_API_KEY"] == SECRET


# ── state B: a key is already there — no gate, no extra click ────────────


def test_a_key_that_is_already_there_adds_no_step(tmp_path):
    with _env(ANTHROPIC_API_KEY=SECRET):
        client, _root = _studio(tmp_path, "haskey")
        page = client.get("/").text

    assert "action=/key" not in page
    assert "Connect the model first" not in page
    assert "Tell me what you want to build" in page  # straight into the flow
    # No strip either: a key that was always there is not news.
    assert "A key is set for this process" not in page


def test_a_mounted_secret_file_counts_as_a_key(tmp_path):
    """The Docker/K8s convention providers/ already honours."""
    keyfile = tmp_path / "key.txt"
    keyfile.write_text(SECRET, encoding="utf-8")
    with _env(ANTHROPIC_API_KEY_FILE=str(keyfile)):
        assert provider_key_present("anthropic")
        client, _root = _studio(tmp_path, "mounted")
        assert "action=/key" not in client.get("/").text


def test_an_unreadable_secret_mount_is_left_to_its_own_loud_failure(tmp_path):
    """A configured *_FILE that cannot be read raises at the provider with
    a message about the mount. Standing in front of it with a paste box
    would hide the real problem behind the wrong question."""
    with _env(ANTHROPIC_API_KEY_FILE=str(tmp_path / "nope")):
        assert provider_key_present("anthropic")


# ── state C: a key that gets refused ─────────────────────────────────────


def test_a_refused_key_puts_the_fix_on_the_page_that_names_it(tmp_path):
    import ai_venture_studio.upstream.autopilot as autopilot

    with _env(ANTHROPIC_API_KEY="sk-ant-wrong"):
        client, _root = _studio(tmp_path, "refused")
        original = autopilot.run_autopilot

        def boom(*a, **k):
            raise RuntimeError("401 unauthorized: invalid x-api-key")

        autopilot.run_autopilot = boom
        try:
            page = client.post(
                "/fdr", data={"fdr": "# a\nb\n"}, follow_redirects=True
            ).text
        finally:
            autopilot.run_autopilot = original

    assert "did not finish" in page
    assert "Paste a working one here" in page or "paste a working one" in page.lower()
    assert "action=/key" in page


def test_a_busy_provider_does_not_get_the_key_form(tmp_path):
    """The whole point of failure_cause: a 529 on a valid, funded key must
    not send someone looking for a key problem that does not exist."""
    import ai_venture_studio.upstream.autopilot as autopilot

    with _env(ANTHROPIC_API_KEY=SECRET):
        client, _root = _studio(tmp_path, "busy")
        original = autopilot.run_autopilot

        def boom(*a, **k):
            raise RuntimeError("529 overloaded_error")

        autopilot.run_autopilot = boom
        try:
            page = client.post(
                "/fdr", data={"fdr": "# a\nb\n"}, follow_redirects=True
            ).text
        finally:
            autopilot.run_autopilot = original

    assert "did not finish" in page
    assert "action=/key" not in page


# ── the shared Studio: "this process only" is true and still misleading ───


def _shared_studio(tmp_path, name):
    """A token-gated Studio — the shared-machine deployment. The token is
    read once at app construction, so it must be set before create."""
    with _env(ANTHROPIC_API_KEY=None, AVS_STUDIO_TOKEN="shared-secret"):
        client, root = _studio(tmp_path, name)
        client.cookies.set("studio_token", "shared-secret")
        return client, root


def test_a_shared_studio_does_not_offer_the_paste_box(tmp_path):
    """AVS_STUDIO_TOKEN means more than one person can reach this process.
    A key pasted into it is spent by all of them, while the form says "this
    process only" — which a reader hears as "my session only"."""
    with _env(AVS_STUDIO_TOKEN="shared-secret"):
        client, _root = _studio(tmp_path, "shared")
        client.cookies.set("studio_token", "shared-secret")
        page = client.get("/").text

    assert "action=/key" not in page, "a shared Studio offered the paste box"
    # …and says why, because silence reads as a broken page on the one
    # deployment where "set it in the environment" is the whole answer.
    assert "shared" in page.lower()
    assert "spend your money" in page or "environment" in page
    # The keyless gate still stands — it just points at the other doors.
    assert "AVS_ANTHROPIC_MODE=bedrock" in page


def test_a_shared_studio_refuses_a_hand_posted_key(tmp_path):
    """The form is absent, so reaching /key is a stale tab or a hand-rolled
    POST. Accepting either would charge one person for everybody."""
    with _env(AVS_STUDIO_TOKEN="shared-secret"):
        client, root = _studio(tmp_path, "sharedpost")
        client.cookies.set("studio_token", "shared-secret")
        page = client.post("/key", data={"key": SECRET}).text

        import os

        assert os.environ.get("ANTHROPIC_API_KEY") != SECRET, (
            "a token-gated Studio accepted a pasted key"
        )
    assert "shared" in page.lower()
    assert SECRET not in page
    # Nowhere on disk either.
    for path in root.rglob("*"):
        if path.is_file():
            assert SECRET not in path.read_text(encoding="utf-8", errors="ignore")


def test_a_localhost_studio_still_offers_it(tmp_path):
    """The single-founder case is untouched: no token, box present."""
    with _env():
        client, _root = _studio(tmp_path, "solo")
        assert "action=/key" in client.get("/").text
