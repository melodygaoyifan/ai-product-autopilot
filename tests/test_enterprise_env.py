"""Enterprise-environment surface: GitLab webhooks, CI-triggered targets,
mounted-file secrets, gateway base URLs, recognized-but-unsupported forges,
and cross-platform process probes. All hermetic."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ai_venture_studio.server import create_app

SECRET = "test-webhook-secret"


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOPRODUCT_WEBHOOK_SECRET", SECRET)
    spawned: list[list[str]] = []

    def fake_spawn(args, repo_dir):
        spawned.append(args)
        return 4242

    client = TestClient(create_app(str(tmp_path), spawn=fake_spawn))
    return client, spawned


MR_URL = "https://gitlab.acme-internal.com/data/mapop/-/merge_requests/26"


def _mr_payload(action: str, **attrs) -> bytes:
    return json.dumps({
        "object_kind": "merge_request",
        "object_attributes": {"iid": 26, "action": action, "url": MR_URL, **attrs},
    }).encode()


# --- GitLab webhook -----------------------------------------------------------


def test_gitlab_open_queues_review(harness):
    client, spawned = harness
    response = client.post(
        "/webhook/gitlab", content=_mr_payload("open"),
        headers={"X-Gitlab-Token": SECRET},
    )
    assert response.status_code == 202 and response.json()["queued"] is True
    assert spawned == [["review", MR_URL]]


def test_gitlab_bad_token_rejected_before_parsing(harness):
    client, spawned = harness
    response = client.post(
        "/webhook/gitlab", content=b"not even json",
        headers={"X-Gitlab-Token": "wrong"},
    )
    assert response.status_code == 401
    assert spawned == []


def test_gitlab_missing_token_rejected(harness):
    client, spawned = harness
    assert client.post("/webhook/gitlab", content=_mr_payload("open")).status_code == 401
    assert spawned == []


def test_gitlab_update_without_new_commits_is_ignored(harness):
    """Title/label/assignee edits arrive as `update` with no oldrev —
    re-reviewing each metadata touch would spam the MR."""
    client, spawned = harness
    response = client.post(
        "/webhook/gitlab", content=_mr_payload("update"),
        headers={"X-Gitlab-Token": SECRET},
    )
    assert response.json()["queued"] is False
    response = client.post(
        "/webhook/gitlab", content=_mr_payload("update", oldrev="abc123"),
        headers={"X-Gitlab-Token": SECRET},
    )
    assert response.json()["queued"] is True
    assert spawned == [["review", MR_URL]]


def test_gitlab_non_mr_events_and_merge_actions_ignored(harness):
    client, spawned = harness
    for content in (
        json.dumps({"object_kind": "push"}).encode(),
        _mr_payload("merge"),
        _mr_payload("approved"),
    ):
        response = client.post(
            "/webhook/gitlab", content=content,
            headers={"X-Gitlab-Token": SECRET},
        )
        assert response.status_code == 202 and response.json()["queued"] is False
    assert spawned == []


# --- CI-triggered targets (the webhook-less entry point) ----------------------


def test_ci_target_gitlab_merge_request_pipeline():
    from ai_venture_studio.ci import detect_ci_target

    target = detect_ci_target({
        "GITLAB_CI": "true",
        "CI_MERGE_REQUEST_IID": "26",
        "CI_PROJECT_URL": "https://gitlab.acme-internal.com/data/mapop",
    })
    assert target == MR_URL


def test_ci_target_gitlab_branch_pipeline_says_how_to_fix():
    from ai_venture_studio.ci import CITargetError, detect_ci_target

    with pytest.raises(CITargetError, match="merge_request_event"):
        detect_ci_target({"GITLAB_CI": "true"})


def test_ci_target_github_actions_reads_event_payload(tmp_path):
    from ai_venture_studio.ci import detect_ci_target

    event = tmp_path / "event.json"
    event.write_text(json.dumps(
        {"pull_request": {"html_url": "https://github.com/x/y/pull/7"}}
    ))
    target = detect_ci_target({
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_EVENT_PATH": str(event),
    })
    assert target == "https://github.com/x/y/pull/7"


def test_ci_target_azure_is_named_not_guessed():
    from ai_venture_studio.ci import CITargetError, detect_ci_target

    with pytest.raises(CITargetError, match="Azure"):
        detect_ci_target({"TF_BUILD": "True"})


def test_ci_target_no_ci_env_is_an_error():
    from ai_venture_studio.ci import CITargetError, detect_ci_target

    with pytest.raises(CITargetError, match="no supported CI environment"):
        detect_ci_target({})


# --- recognized-but-unsupported forges ----------------------------------------


def test_unsupported_forges_are_named_never_git_diffed():
    from ai_venture_studio.forge import recognize_unsupported

    assert recognize_unsupported(
        "https://dev.azure.com/acme/proj/_git/repo/pullrequest/12"
    ) == "Azure DevOps"
    assert recognize_unsupported(
        "https://git.acme-internal.com/projects/DATA/repos/mapop/pull-requests/3"
    ) == "Bitbucket"
    assert recognize_unsupported("https://github.com/x/y/pull/7") is None
    assert recognize_unsupported("main...HEAD") is None


# --- mounted-file secrets (K8s/Docker) ----------------------------------------


def test_env_or_file_reads_mounted_secret(tmp_path):
    from ai_venture_studio.secrets import env_or_file

    mount = tmp_path / "api-key"
    mount.write_text("sk-mounted\n")
    assert env_or_file("MY_KEY", {"MY_KEY_FILE": str(mount)}) == "sk-mounted"
    assert env_or_file("MY_KEY", {"MY_KEY": "sk-env"}) == "sk-env"
    assert env_or_file("MY_KEY", {}) is None


def test_env_or_file_unreadable_mount_errors_loudly(tmp_path):
    from ai_venture_studio.secrets import SecretError, env_or_file

    with pytest.raises(SecretError, match="could not be read"):
        env_or_file("MY_KEY", {"MY_KEY_FILE": str(tmp_path / "absent")})


def test_secret_ref_resolves_through_file_mount(tmp_path):
    from ai_venture_studio.secrets import SecretsLoader

    mount = tmp_path / "token"
    mount.write_text("t0k3n")
    loader = SecretsLoader({"SENTRY_TOKEN_FILE": str(mount)})
    assert loader.resolve("secret://SENTRY_TOKEN").reveal() == "t0k3n"


# --- gateway base URLs for the non-Anthropic seats ----------------------------


def test_openai_seat_honors_gateway_base_url(monkeypatch):
    from ai_venture_studio.providers import openai_compat

    calls = {}

    def fake_post(url, **kwargs):
        calls["url"] = url

        class R:
            status_code = 200
            text = ""

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "ok"},
                                     "finish_reason": "stop"}]}

        return R()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://llm-gateway.acme.com/v1/")
    monkeypatch.setattr(openai_compat.httpx, "post", fake_post)
    out = openai_compat.OpenAIProvider().complete(
        model="gpt-4o", system="s", user="u"
    )
    assert out == "ok"
    assert calls["url"] == "https://llm-gateway.acme.com/v1/chat/completions"


# --- cross-platform process probe ---------------------------------------------


def test_pid_alive_true_for_self_false_for_bogus():
    import os

    from ai_venture_studio.procs import pid_alive

    assert pid_alive(os.getpid()) is True
    assert pid_alive(-1) is False
    # 2**22 exceeds the default pid_max on Linux and practical pids on macOS.
    assert pid_alive(2**22 + 1) in (True, False)  # never raises, never kills


# --- enterprise-web profile ---------------------------------------------------


def test_enterprise_web_profile_loads_and_seeds_governance(tmp_path):
    from ai_venture_studio.upstream.workspace import (
        available_profiles,
        init_workspace,
        load_profile,
    )

    assert "enterprise-web" in available_profiles()
    data = load_profile("enterprise-web")
    joined = " ".join(data["constraints"])
    for must in ("audit record", "/api/health", "environment variable", "_FILE"):
        assert must in joined
    root = init_workspace(tmp_path / "ws", "pilot", "enterprise-web")
    claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "enterprise-web" in claude and "append-only" in claude


def test_enterprise_web_reuses_web_block_library():
    from ai_venture_studio.upstream.blocks import list_blocks

    assert list_blocks("enterprise-web") == list_blocks("web")


# --- studio worker inherits the provider --------------------------------------


def test_studio_build_worker_inherits_provider(tmp_path, monkeypatch):
    """A Studio started with --provider mock spawned a build worker that
    wanted a real key and died silently (output was DEVNULL). The worker
    must inherit the provider and leave a build.log behind."""
    from fastapi.testclient import TestClient as _TC

    from ai_venture_studio import studio as studio_mod
    from ai_venture_studio.upstream.workspace import init_workspace

    root = init_workspace(tmp_path / "ws", "pilot", "web")
    argv_seen = {}

    class FakeProc:
        pid = 4242

    def fake_popen(argv, **kwargs):
        argv_seen["argv"] = list(argv)
        argv_seen["stdout_is_devnull"] = kwargs.get("stdout") == -3  # subprocess.DEVNULL
        return FakeProc()

    monkeypatch.setattr(studio_mod.subprocess, "Popen", fake_popen)
    client = _TC(studio_mod.create_studio_app(root, provider="mock"))
    response = client.post("/build", follow_redirects=False)
    assert response.status_code == 303
    argv = argv_seen["argv"]
    assert "--provider" in argv and argv[argv.index("--provider") + 1] == "mock"
    assert argv_seen["stdout_is_devnull"] is False
