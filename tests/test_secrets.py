"""D16: the secrets layer — loud resolution, masked repr, outbound scrub."""

import pytest

from autoproduct.secrets import Secret, SecretError, SecretsLoader


def test_secret_never_reprs_its_value():
    secret = Secret("API_KEY", "sk-super-sensitive")
    assert "sk-super-sensitive" not in repr(secret)
    assert "sk-super-sensitive" not in str(secret)
    assert "sk-super-sensitive" not in f"{secret}"
    assert secret.reveal() == "sk-super-sensitive"


def test_resolve_from_environ():
    loader = SecretsLoader({"ANTHROPIC_API_KEY": "sk-live-1"})
    assert loader.resolve("secret://ANTHROPIC_API_KEY").reveal() == "sk-live-1"


def test_missing_secret_errors_loudly():
    loader = SecretsLoader({})
    with pytest.raises(SecretError, match="not set"):
        loader.resolve("secret://NOPE")


def test_empty_value_counts_as_missing():
    loader = SecretsLoader({"EMPTY": ""})
    with pytest.raises(SecretError, match="not set"):
        loader.resolve("secret://EMPTY")


def test_non_reference_refused():
    with pytest.raises(SecretError, match="secret://"):
        SecretsLoader({}).resolve("plain-string")


def test_scrub_strips_every_resolved_value():
    loader = SecretsLoader({"A": "alpha-token", "B": "beta-token"})
    loader.resolve("secret://A")
    loader.resolve("secret://B")
    out = loader.scrub("log line with alpha-token and beta-token inside")
    assert "alpha-token" not in out and "beta-token" not in out
    assert "<secret:A>" in out and "<secret:B>" in out


def test_scrub_ignores_unresolved_env():
    loader = SecretsLoader({"A": "alpha-token", "UNTOUCHED": "ghost"})
    loader.resolve("secret://A")
    assert "ghost" in loader.scrub("ghost stays: never resolved, never known")
