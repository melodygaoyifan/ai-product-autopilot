"""v0.38.0 — multi-tenant server mode (ADR-030).

The load-bearing tests are the isolation ones: a token reaches exactly one
workspace, containment is refused at load time, and no response
enumerates tenants.
"""

from __future__ import annotations

import hmac
import json
import pathlib

import pytest
import yaml
from fastapi.testclient import TestClient

from autoproduct.server import create_app
from autoproduct.tenants import (
    Tenant,
    TenantError,
    add_tenant,
    hash_token,
    load_tenants,
    multi_tenant,
    resolve_tenant,
)


def _workspace(root: pathlib.Path, name: str) -> pathlib.Path:
    path = root / name
    (path / ".mas").mkdir(parents=True, exist_ok=True)
    return path


def _registry(root: pathlib.Path, entries: list[dict]) -> None:
    (root / ".mas").mkdir(parents=True, exist_ok=True)
    (root / ".mas" / "tenants.yaml").write_text(
        yaml.safe_dump({"tenants": entries}), encoding="utf-8"
    )


# --- registry validation -------------------------------------------------------


def test_absent_registry_means_single_tenant(tmp_path):
    assert multi_tenant(tmp_path) is False
    assert load_tenants(tmp_path) == []


def test_add_tenant_stores_only_a_hash_and_returns_the_token_once(tmp_path):
    ws = _workspace(tmp_path, "acme")
    tenant, token = add_tenant(tmp_path, "acme", ws)
    assert tenant.token_sha256 == hash_token(token)
    raw = (tmp_path / ".mas" / "tenants.yaml").read_text()
    assert token not in raw  # plaintext never lands on disk
    assert tenant.token_sha256 in raw
    assert multi_tenant(tmp_path) is True


def test_contained_workspaces_are_refused(tmp_path):
    outer = _workspace(tmp_path, "outer")
    inner = _workspace(tmp_path, "outer/inner")
    _registry(tmp_path, [
        {"id": "a", "token_sha256": hash_token("t1"), "workspace": str(outer)},
        {"id": "b", "token_sha256": hash_token("t2"), "workspace": str(inner)},
    ])
    with pytest.raises(TenantError, match="must be disjoint"):
        load_tenants(tmp_path)


def test_identical_workspaces_are_refused(tmp_path):
    ws = _workspace(tmp_path, "shared")
    _registry(tmp_path, [
        {"id": "a", "token_sha256": hash_token("t1"), "workspace": str(ws)},
        {"id": "b", "token_sha256": hash_token("t2"), "workspace": str(ws)},
    ])
    with pytest.raises(TenantError, match="must be disjoint"):
        load_tenants(tmp_path)


def test_shared_token_is_refused(tmp_path):
    _registry(tmp_path, [
        {"id": "a", "token_sha256": hash_token("same"),
         "workspace": str(_workspace(tmp_path, "a"))},
        {"id": "b", "token_sha256": hash_token("same"),
         "workspace": str(_workspace(tmp_path, "b"))},
    ])
    with pytest.raises(TenantError, match="share a token"):
        load_tenants(tmp_path)


@pytest.mark.parametrize(("entry", "match"), [
    ({"id": "bad id!", "token_sha256": "a" * 64, "workspace": "/tmp"}, "must be"),
    ({"id": "ok", "token_sha256": "short", "workspace": "/tmp"}, "64-char"),
    ({"id": "", "token_sha256": "a" * 64, "workspace": "/tmp"}, "must be"),
])
def test_malformed_entries_fail_loudly(tmp_path, entry, match):
    _registry(tmp_path, [entry])
    with pytest.raises(TenantError, match=match):
        load_tenants(tmp_path)


def test_duplicate_ids_refused(tmp_path):
    _registry(tmp_path, [
        {"id": "a", "token_sha256": hash_token("t1"),
         "workspace": str(_workspace(tmp_path, "one"))},
        {"id": "a", "token_sha256": hash_token("t2"),
         "workspace": str(_workspace(tmp_path, "two"))},
    ])
    with pytest.raises(TenantError, match="duplicate tenant id"):
        load_tenants(tmp_path)


def test_add_tenant_rolls_back_a_registry_it_would_invalidate(tmp_path):
    ws = _workspace(tmp_path, "acme")
    add_tenant(tmp_path, "acme", ws)
    before = (tmp_path / ".mas" / "tenants.yaml").read_text()
    with pytest.raises(TenantError, match="must be disjoint"):
        add_tenant(tmp_path, "beta", ws / "nested")
    assert (tmp_path / ".mas" / "tenants.yaml").read_text() == before


def test_resolve_ignores_disabled_and_unknown(tmp_path):
    tenants = [
        Tenant(id="live", token_sha256=hash_token("good"), workspace=str(tmp_path)),
        Tenant(id="off", token_sha256=hash_token("stale"), workspace=str(tmp_path),
               enabled=False),
    ]
    assert resolve_tenant(tenants, "good").id == "live"
    assert resolve_tenant(tenants, "stale") is None
    assert resolve_tenant(tenants, "nope") is None
    assert resolve_tenant(tenants, "") is None


# --- server isolation ----------------------------------------------------------


@pytest.fixture
def two_tenants(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTOPRODUCT_WEBHOOK_SECRET", raising=False)
    acme = _workspace(tmp_path, "acme")
    beta = _workspace(tmp_path, "beta")
    _registry(tmp_path, [
        {"id": "acme", "token_sha256": hash_token("acme-token"),
         "workspace": str(acme),
         "webhook_secret_ref": "secret://ACME_WEBHOOK"},
        {"id": "beta", "token_sha256": hash_token("beta-token"),
         "workspace": str(beta)},
    ])
    spawned: list[tuple[list[str], str]] = []
    client = TestClient(create_app(
        str(tmp_path), spawn=lambda args, repo: spawned.append((args, repo)) or 1
    ))
    return client, acme, beta, spawned


def test_healthz_reports_tenant_mode(two_tenants):
    client, *_ = two_tenants
    assert client.get("/healthz").json() == {"ok": True, "tenants": 2}


def test_incident_lands_in_the_tokens_own_workspace(two_tenants):
    client, acme, beta, spawned = two_tenants
    response = client.post(
        "/incidents", json={"title": "acme outage"},
        headers={"Authorization": "Bearer acme-token"},
    )
    assert response.status_code == 202
    assert list((acme / ".mas" / "inbox").glob("*.yaml"))
    assert not (beta / ".mas" / "inbox").exists()
    # The worker runs in the tenant's workspace, not the served root.
    assert spawned[0][1] == str(acme)


def test_unknown_disabled_and_missing_tokens_answer_identically(two_tenants):
    client, *_ = two_tenants
    bodies = set()
    for headers in (
        {},
        {"Authorization": "Bearer wrong"},
        {"Authorization": "Bearer acme-toke"},  # near-miss
    ):
        response = client.post("/incidents", json={"title": "x"}, headers=headers)
        assert response.status_code == 401
        bodies.add(response.text)
    assert len(bodies) == 1, "responses must not distinguish tenant existence"


def test_reviews_are_not_readable_across_tenants(two_tenants):
    client, acme, beta, _ = two_tenants
    for ws, review_id, verdict in ((acme, "aaa111", "APPROVE"),
                                   (beta, "bbb222", "REQUEST_CHANGES")):
        review_dir = ws / ".mas" / "reviews" / review_id
        review_dir.mkdir(parents=True)
        (review_dir / "01-final.yaml").write_text(
            yaml.safe_dump({"verdict": verdict, "target": f"{ws.name}-pr"}),
            encoding="utf-8",
        )
    acme_rows = client.get(
        "/reviews", headers={"Authorization": "Bearer acme-token"}
    ).json()
    assert [r["review_id"] for r in acme_rows] == ["aaa111"]
    beta_rows = client.get(
        "/reviews", headers={"Authorization": "Bearer beta-token"}
    ).json()
    assert [r["review_id"] for r in beta_rows] == ["bbb222"]
    # No token, no listing.
    assert client.get("/reviews").status_code == 401
    # And one tenant cannot fetch the other's detail by id.
    assert client.get(
        "/reviews/bbb222", headers={"Authorization": "Bearer acme-token"}
    ).status_code == 404


def test_review_id_traversal_is_rejected(two_tenants):
    client, *_ = two_tenants
    response = client.get(
        "/reviews/..%2F..%2F..%2Fbeta%2F.mas%2Freviews%2Fbbb222",
        headers={"Authorization": "Bearer acme-token"},
    )
    assert response.status_code in (404, 422)  # never 200
    response = client.get(
        "/reviews/a b", headers={"Authorization": "Bearer acme-token"}
    )
    assert response.status_code == 422


def test_jobs_listing_is_tenant_scoped(two_tenants):
    client, acme, beta, _ = two_tenants
    (acme / ".mas" / "jobs.yaml").write_text(
        yaml.safe_dump([{"pid": 1, "args": ["review", "acme-pr"], "status": "finished"}]),
        encoding="utf-8",
    )
    (beta / ".mas" / "jobs.yaml").write_text(
        yaml.safe_dump([{"pid": 2, "args": ["review", "beta-pr"], "status": "finished"}]),
        encoding="utf-8",
    )
    rows = client.get("/jobs", headers={"Authorization": "Bearer acme-token"}).json()
    assert json.dumps(rows).count("acme-pr") == 1
    assert "beta-pr" not in json.dumps(rows)


# --- per-tenant GitHub webhook secrets ----------------------------------------


def _signature(secret: str, body: bytes) -> str:
    import hashlib

    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_github_delivery_verifies_against_the_named_tenants_secret(
    two_tenants, monkeypatch
):
    client, acme, _beta, spawned = two_tenants
    monkeypatch.setenv("ACME_WEBHOOK", "acme-hook-secret")
    payload = {"action": "opened",
               "pull_request": {"html_url": "https://github.com/acme/x/pull/1"}}
    body = json.dumps(payload).encode()
    response = client.post(
        "/webhook/github/acme", content=body,
        headers={"X-GitHub-Event": "pull_request",
                 "X-Hub-Signature-256": _signature("acme-hook-secret", body)},
    )
    assert response.status_code == 202
    assert spawned[-1][1] == str(acme)

    # Another tenant's (or a guessed) secret does not verify.
    response = client.post(
        "/webhook/github/acme", content=body,
        headers={"X-GitHub-Event": "pull_request",
                 "X-Hub-Signature-256": _signature("wrong-secret", body)},
    )
    assert response.status_code == 401


def test_tenant_without_a_configured_secret_accepts_no_deliveries(two_tenants):
    client, *_ = two_tenants
    payload = {"action": "opened", "pull_request": {"html_url": "u"}}
    body = json.dumps(payload).encode()
    response = client.post(
        "/webhook/github/beta", content=body,
        headers={"X-GitHub-Event": "pull_request",
                 "X-Hub-Signature-256": _signature("anything", body)},
    )
    assert response.status_code == 401


def test_unknown_tenant_path_looks_like_a_bad_signature(two_tenants, monkeypatch):
    """404-vs-401 would enumerate tenants; both answer 401."""
    client, *_ = two_tenants
    monkeypatch.setenv("ACME_WEBHOOK", "acme-hook-secret")
    body = json.dumps({"action": "opened", "pull_request": {"html_url": "u"}}).encode()
    response = client.post(
        "/webhook/github/ghost", content=body,
        headers={"X-GitHub-Event": "pull_request",
                 "X-Hub-Signature-256": _signature("acme-hook-secret", body)},
    )
    assert response.status_code == 401


def test_multi_tenant_rejects_the_untenanted_github_path(two_tenants):
    client, *_ = two_tenants
    response = client.post(
        "/webhook/github", content=b"{}",
        headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "sha256=x"},
    )
    assert response.status_code == 404
    assert "tenant_id" in response.text


# --- single-tenant mode is unchanged ------------------------------------------


def test_single_tenant_mode_keeps_the_shared_secret_path(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOPRODUCT_WEBHOOK_SECRET", "shared")
    (tmp_path / ".mas").mkdir()
    client = TestClient(create_app(str(tmp_path), spawn=lambda args, repo: 1))
    assert client.get("/healthz").json() == {"ok": True, "tenants": None}
    assert client.post(
        "/incidents", json={"title": "x"},
        headers={"Authorization": "Bearer shared"},
    ).status_code == 202
    assert client.post("/incidents", json={"title": "x"},
                       headers={"Authorization": "Bearer nope"}).status_code == 401
    # Reads stay open on the localhost dashboard, as before.
    assert client.get("/reviews").status_code == 200
    # And the tenanted webhook path does not exist here.
    assert client.post(
        "/webhook/github/acme", content=b"{}",
        headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "sha256=x"},
    ).status_code == 404
