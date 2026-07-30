"""Enterprise provider routing (AVS_ANTHROPIC_MODE): direct API, gateway
bearer tokens, Bedrock, Vertex. Hermetic — the anthropic client classes are
stubbed; nothing constructs a real client or touches a network."""

from __future__ import annotations

import anthropic
import pytest

from ai_venture_studio.providers.anthropic_provider import _make_client
from ai_venture_studio.providers.base import ProviderError

_MODE_VARS = (
    "AVS_ANTHROPIC_MODE", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY_FILE", "ANTHROPIC_AUTH_TOKEN_FILE",
    "ANTHROPIC_VERTEX_PROJECT_ID", "CLOUD_ML_REGION",
    "ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_RESOURCE",
    "ANTHROPIC_FOUNDRY_BASE_URL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in _MODE_VARS:
        monkeypatch.delenv(var, raising=False)


def test_direct_mode_without_any_credential_errors_loudly():
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY is not set"):
        _make_client()


def test_direct_mode_accepts_gateway_bearer_token(monkeypatch):
    """Enterprise LLM gateways authenticate with ANTHROPIC_AUTH_TOKEN +
    ANTHROPIC_BASE_URL; the absence of an API key must not block them."""
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "gw-token")
    captured = {}

    def fake_anthropic(api_key=None, auth_token=None):
        captured["auth_token"] = auth_token
        return "direct-client"

    monkeypatch.setattr(anthropic, "Anthropic", fake_anthropic)
    assert _make_client() == "direct-client"
    assert captured["auth_token"] == "gw-token"


def test_unknown_mode_is_an_error_not_a_silent_fallback(monkeypatch):
    monkeypatch.setenv("AVS_ANTHROPIC_MODE", "azure")
    with pytest.raises(ProviderError, match="unknown AVS_ANTHROPIC_MODE"):
        _make_client()


def test_bedrock_mode_selects_bedrock_client(monkeypatch):
    monkeypatch.setenv("AVS_ANTHROPIC_MODE", "bedrock")
    monkeypatch.setattr(
        anthropic, "AnthropicBedrock", lambda: "bedrock-client", raising=False
    )
    assert _make_client() == "bedrock-client"


def test_bedrock_startup_failure_says_what_is_missing(monkeypatch):
    monkeypatch.setenv("AVS_ANTHROPIC_MODE", "bedrock")

    def _boom():
        raise RuntimeError("boto3 is required")

    monkeypatch.setattr(anthropic, "AnthropicBedrock", _boom, raising=False)
    with pytest.raises(ProviderError, match="anthropic\\[bedrock\\]"):
        _make_client()


def test_vertex_mode_requires_project_and_region(monkeypatch):
    monkeypatch.setenv("AVS_ANTHROPIC_MODE", "vertex")
    with pytest.raises(ProviderError, match="ANTHROPIC_VERTEX_PROJECT_ID"):
        _make_client()


def test_vertex_mode_selects_vertex_client(monkeypatch):
    monkeypatch.setenv("AVS_ANTHROPIC_MODE", "vertex")
    monkeypatch.setenv("ANTHROPIC_VERTEX_PROJECT_ID", "acme-ml")
    monkeypatch.setenv("CLOUD_ML_REGION", "us-east5")
    monkeypatch.setattr(
        anthropic, "AnthropicVertex", lambda: "vertex-client", raising=False
    )
    assert _make_client() == "vertex-client"


def test_foundry_mode_requires_key_and_resource(monkeypatch):
    monkeypatch.setenv("AVS_ANTHROPIC_MODE", "foundry")
    with pytest.raises(ProviderError, match="ANTHROPIC_FOUNDRY_API_KEY"):
        _make_client()


def test_foundry_mode_selects_foundry_client(monkeypatch):
    monkeypatch.setenv("AVS_ANTHROPIC_MODE", "foundry")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "az-key")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "acme-ai")
    monkeypatch.setattr(
        anthropic, "AnthropicFoundry",
        lambda api_key=None: f"foundry-client:{api_key}", raising=False,
    )
    assert _make_client() == "foundry-client:az-key"


def test_direct_mode_accepts_file_mounted_key(monkeypatch, tmp_path):
    """K8s/Docker secret mounts deliver the key as a file, not an env var."""
    mount = tmp_path / "anthropic-key"
    mount.write_text("sk-mounted")
    monkeypatch.setenv("ANTHROPIC_API_KEY_FILE", str(mount))
    captured = {}

    def fake_anthropic(api_key=None, auth_token=None):
        captured["api_key"] = api_key
        return "direct-client"

    monkeypatch.setattr(anthropic, "Anthropic", fake_anthropic)
    assert _make_client() == "direct-client"
    assert captured["api_key"] == "sk-mounted"
