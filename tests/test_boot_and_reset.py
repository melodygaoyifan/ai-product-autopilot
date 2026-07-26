"""Run-4 case-03 regressions: the boot contract, failure forensics, and
workspace hygiene (see .mas/product-bench forensics, 2026-07-26)."""

import shutil
import subprocess

import pytest

from autoproduct.upstream.build import (
    _boot_gate,
    _preserve_failed_attempt,
    _reset_workspace,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)

_SERVER = """\
import os, socket, time
s = socket.socket()
s.bind(("127.0.0.1", int(os.environ["PORT"])))
s.listen()
time.sleep(30)
"""


def test_boot_gate_passes_when_entry_serves_on_port(tmp_path):
    (tmp_path / "main.py").write_text(_SERVER)
    assert _boot_gate(tmp_path) is None


def test_boot_gate_fails_when_entry_exits_without_serving(tmp_path):
    """Idiomatic FastAPI module without a __main__ block: defines app,
    exits — run 4's 'server never listened' on every probe."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("app = object()\n")
    failure = _boot_gate(tmp_path)
    assert failure is not None and "BOOT GATE" in failure and "exited" in failure
    assert "__main__" in failure  # feedback teaches the fix, not just the fact


def test_boot_gate_skips_when_no_entry_point(tmp_path):
    (tmp_path / "lib.py").write_text("x = 1\n")
    assert _boot_gate(tmp_path) is None


def _git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.email=t@local", "-c", "user.name=t", *args],
        cwd=repo, check=True, capture_output=True,
    )


def test_preserve_and_reset_after_failed_in_place_build(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text(".mas/\n")  # as init_workspace writes
    (tmp_path / "a.py").write_text("original\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    pre_existing = {"a.py"}

    # A failed attempt's residue: modified tracked file + new files.
    (tmp_path / "a.py").write_text("dirtied by failed attempt\n")
    (tmp_path / "new_module").mkdir()
    (tmp_path / "new_module" / "b.py").write_text("residue\n")

    preserved = _preserve_failed_attempt(tmp_path, "some-slug")
    _reset_workspace(tmp_path, pre_existing)

    keep = tmp_path / preserved
    assert (keep / "a.py").read_text() == "dirtied by failed attempt\n"
    assert (keep / "new_module" / "b.py").read_text() == "residue\n"
    # Workspace is clean again: tracked restored, residue gone (dir too).
    assert (tmp_path / "a.py").read_text() == "original\n"
    assert not (tmp_path / "new_module").exists()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path,
        capture_output=True, text=True,
    ).stdout
    assert status.strip() == ""


def test_web_profile_carries_scope_law_and_boot_contract():
    from autoproduct.upstream.workspace import load_profile

    profile = load_profile("web")
    text = " ".join(profile["constraints"])
    assert "scope is law" in text
    assert "Where the product includes accounts or login" in text
    assert "BOOT CONTRACT" in profile["stack_hint"]
    assert "PORT" in profile["stack_hint"]
    assert "never crash on user input" in text
    assert "human-readable message" in text


def test_implementer_receives_the_literal_source_contract(tmp_path, monkeypatch):
    """Contract drift migrated to the implementer once specs held it (live
    post-fix test: the scores handler invented "index" for the FDR's
    "item" and every probe died) — the implementer prompt must carry the
    FDR verbatim, via the workspace FDR.md fallback."""
    import autoproduct.upstream.build as build_mod
    from autoproduct.upstream import approve_spec, init_workspace, run_spec_stage

    root = init_workspace(tmp_path / "p", "p", "web")
    spec = run_spec_stage(root, "an item store API", provider="mock")
    approve_spec(root, spec.slug)
    contract = 'scores use the field name "item" and rounds "day5"/"day12"'
    (root / "FDR.md").write_text(contract, encoding="utf-8")

    seen = []

    class Stub:
        def complete(self, **kwargs):
            seen.append(kwargs)
            return "not: [parseable"

    monkeypatch.setattr(build_mod, "get_provider", lambda name: Stub())
    result = build_mod.run_build(root, spec.slug, provider="stub")
    assert result.status == "error"
    prompt = seen[0]["user"]
    assert "<source_contract>" in prompt and '"item"' in prompt
    assert "LITERAL" in seen[0]["system"] and "4xx" in seen[0]["system"]
    assert "additively" in seen[0]["system"] and "tests-only" in seen[0]["system"]


def test_shared_test_fixtures_are_additive_only(tmp_path):
    """conftest/helpers under tests/ are a vocabulary sibling tasks import —
    a rewrite that drops a name is kept out (run 7, case 04: a conftest
    rewrite lost post_json and three straight iterations died on
    ImportError before any test ran)."""
    from autoproduct.upstream.build import _write_files

    (tmp_path / "tests").mkdir()
    conftest = tmp_path / "tests" / "conftest.py"
    conftest.write_text("def post_json(base, path, body):\n    return 1\n")

    # Parallel-vocabulary rewrite dropping post_json: kept out, original intact.
    written, kept = _write_files(
        tmp_path,
        [{"path": "tests/conftest.py",
          "new_content": "def http(base):\n    return 2\n"}],
        allowed_test_paths=set(),
    )
    assert written == [] and len(kept) == 1 and "post_json" in kept[0]
    assert "post_json" in conftest.read_text()

    # Additive extension: written.
    written, kept = _write_files(
        tmp_path,
        [{"path": "tests/conftest.py",
          "new_content": "def post_json(base, path, body):\n    return 1\n\n"
                         "def http(base):\n    return 2\n"}],
        allowed_test_paths=set(),
    )
    assert written == ["tests/conftest.py"] and kept == []


def test_private_names_are_not_vocabulary(tmp_path):
    """A helpers rewrite may restructure _private internals freely — only
    public names sibling tests can import are guarded (run 8, case 01 t3:
    the guard blocked a rewrite over reshuffled _check_url/_do)."""
    from autoproduct.upstream.build import _write_files

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "helpers.py").write_text(
        "def _check_url(u):\n    return u\n\ndef post(base):\n    return 1\n"
    )
    written, kept = _write_files(
        tmp_path,
        [{"path": "tests/helpers.py",
          "new_content": "def post(base):\n    return 1\n\ndef http_post(base):\n    return 2\n"}],
        allowed_test_paths=set(),
    )
    assert written == ["tests/helpers.py"] and kept == []
    # Dropping a PUBLIC name still keeps the file out.
    written, kept = _write_files(
        tmp_path,
        [{"path": "tests/helpers.py",
          "new_content": "def only_new(base):\n    return 3\n"}],
        allowed_test_paths=set(),
    )
    assert written == [] and "post" in kept[0]


def test_stale_import_note_names_phantom_imports(tmp_path):
    """Files persisting across iterations that import names which don't
    exist get a precise deterministic callout in the feedback."""
    from autoproduct.upstream.build import _stale_import_note

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "helpers.py").write_text("def post(base):\n    return 1\n")
    (tmp_path / "tests" / "test_ok.py").write_text("from tests.helpers import post\n")
    assert _stale_import_note(tmp_path) == ""
    (tmp_path / "tests" / "test_stale.py").write_text(
        "from tests.helpers import http_post\n"
    )
    note = _stale_import_note(tmp_path)
    assert "test_stale.py" in note and "http_post" in note and "post" in note
    assert "test_ok.py" not in note
