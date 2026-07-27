"""The secrets layer (doc 09 §3.1, plan D16) — resolution without leakage.

secret:// references resolve from the environment (vault/cloud backends
are gated externals behind the same interface); a missing secret errors
loudly at resolution, values never repr, and scrub() strips any resolved
value from outbound text — the belt for the never-in-prompts suspenders.
"""

from __future__ import annotations

import os


class SecretError(RuntimeError):
    pass


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
        """secret://ENV_NAME → the env value, loudly or not at all."""
        if not ref.startswith("secret://"):
            raise SecretError(f"{ref!r} is not a secret:// reference")
        name = ref.removeprefix("secret://")
        value = self._env.get(name, "")
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
