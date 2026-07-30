"""The secrets layer (doc 09 §3.1, plan D16) — resolution without leakage.

secret:// references resolve from the environment (vault/cloud backends
are gated externals behind the same interface); a missing secret errors
loudly at resolution, values never repr, and scrub() strips any resolved
value from outbound text — the belt for the never-in-prompts suspenders.
"""

from __future__ import annotations

import os
from pathlib import Path


class SecretError(RuntimeError):
    pass


def env_or_file(name: str, environ: dict[str, str] | None = None) -> str | None:
    """NAME from the environment, else the contents of the file NAME_FILE
    points at — the Docker/K8s secret-mount convention, so a key can live
    in a mounted secret instead of a process environment variable. A
    configured NAME_FILE that cannot be read errors loudly: a mount that
    silently resolved to nothing would run half-armed."""
    env = os.environ if environ is None else environ
    value = env.get(name, "")
    if value:
        return value
    path = env.get(f"{name}_FILE", "")
    if not path:
        return None
    try:
        content = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SecretError(f"{name}_FILE={path!r} could not be read: {exc}") from exc
    return content or None


class Secret:
    """A resolved secret that refuses casual exposure."""

    def __init__(self, name: str, value: str):
        self._name = name
        self._value = value

    def reveal(self) -> str:  # the single deliberate access point
        return self._value

    def __repr__(self) -> str:
        return f"Secret({self._name!r}, ****)"

    __str__ = __repr__


class SecretsLoader:
    def __init__(self, environ: dict[str, str] | None = None):
        self._env = dict(environ) if environ is not None else dict(os.environ)
        self._resolved: dict[str, Secret] = {}

    def resolve(self, ref: str) -> Secret:
        """secret://ENV_NAME → the env value (or the NAME_FILE-mounted
        file's contents), loudly or not at all."""
        if not ref.startswith("secret://"):
            raise SecretError(f"{ref!r} is not a secret:// reference")
        name = ref.removeprefix("secret://")
        value = env_or_file(name, self._env) or ""
        if not value:
            raise SecretError(f"secret {name!r} is not set — providers and "
                              "gates error loudly, never run half-armed")
        secret = Secret(name, value)
        self._resolved[name] = secret
        return secret

    def scrub(self, text: str) -> str:
        """Strip every resolved value from outbound text (logs, prompts,
        mirrors) — the leak that cannot happen is the one already scrubbed."""
        for name, secret in self._resolved.items():
            text = text.replace(secret.reveal(), f"<secret:{name}>")
        return text
