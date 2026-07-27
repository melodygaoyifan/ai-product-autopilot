"""Multi-tenant server mode (ADR-030 — a recorded reversal of a non-goal).

"Multi-tenant SaaS" was out of scope in every prior edition (README, doc
18 §ADR-U17). This module reverses the *server* half of that narrowly and
on the record: one `autoproduct serve` process may now front several
isolated workspaces. What stays out is the SaaS half — no billing, no
plans, no shared database, no cross-tenant anything.

The isolation model is deliberately boring, because boring is auditable:

- **A tenant is a token and a directory.** `.mas/tenants.yaml` maps a
  tenant id to a SHA-256 token hash and a workspace root. Plaintext tokens
  are never stored — `tenant-add` prints one once and keeps the hash.
- **Workspaces must be disjoint.** Registry loading refuses two tenants
  sharing a root, or one root containing another. Containment is the
  failure mode that turns "isolated" into a word rather than a property.
- **Every request resolves to exactly one workspace**, chosen by the
  token, never by a client-supplied path or id.
- **Per-tenant webhook secrets** are `secret://ENV` references resolved
  through the v0.31 secrets layer, so one tenant's GitHub secret cannot
  verify another's deliveries and no secret sits in the registry file.
- **Single-tenant mode is unchanged.** No `tenants.yaml`, no multi-tenancy:
  the shared-secret path stays exactly as it was.
"""

from __future__ import annotations

import hashlib
import hmac
import pathlib
import secrets as secrets_mod

import yaml
from pydantic import BaseModel, Field

TENANTS_FILE = "tenants.yaml"
TOKEN_BYTES = 32
_ID_OK = set("abcdefghijklmnopqrstuvwxyz0123456789-_")


class TenantError(RuntimeError):
    """A registry that cannot be honored — never a partial load."""


class Tenant(BaseModel):
    id: str
    token_sha256: str
    workspace: str
    enabled: bool = True
    webhook_secret_ref: str = Field(
        default="",
        description="secret://ENV_NAME holding this tenant's GitHub webhook "
        "secret; empty means this tenant accepts no GitHub deliveries",
    )

    def webhook_secret(self) -> str | None:
        """Resolve the tenant's webhook secret, or None when unconfigured.
        A configured-but-unset reference is an error, not a fallback."""
        if not self.webhook_secret_ref:
            return None
        from autoproduct.secrets import SecretsLoader

        return SecretsLoader().resolve(self.webhook_secret_ref).reveal()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets_mod.token_urlsafe(TOKEN_BYTES)


def registry_path(repo_dir: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(repo_dir) / ".mas" / TENANTS_FILE


def multi_tenant(repo_dir: str | pathlib.Path) -> bool:
    return registry_path(repo_dir).exists()


def load_tenants(repo_dir: str | pathlib.Path) -> list[Tenant]:
    """Load and validate the registry. Absent file → [] (single-tenant)."""
    path = registry_path(repo_dir)
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise TenantError(f"{path} is not parseable YAML: {exc}") from exc
    entries = raw.get("tenants") if isinstance(raw, dict) else raw
    if not isinstance(entries, list) or not entries:
        raise TenantError(f"{path} must hold a non-empty `tenants:` list")

    tenants: list[Tenant] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise TenantError(f"{path}: each tenant must be a mapping, got {entry!r}")
        try:
            tenant = Tenant.model_validate(entry)
        except Exception as exc:  # noqa: BLE001 — surfaced as TenantError
            raise TenantError(f"{path}: invalid tenant entry {entry!r}: {exc}") from exc
        if not tenant.id or set(tenant.id) - _ID_OK:
            raise TenantError(
                f"{path}: tenant id {tenant.id!r} must be non-empty and use only "
                "[a-z0-9-_] — ids appear in URLs and paths"
            )
        if len(tenant.token_sha256) != 64:
            raise TenantError(
                f"{path}: tenant {tenant.id!r} token_sha256 must be a 64-char "
                "SHA-256 hex digest (plaintext tokens are never stored)"
            )
        tenants.append(tenant)

    ids = [t.id for t in tenants]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise TenantError(f"{path}: duplicate tenant id(s) {duplicates}")

    digests = [t.token_sha256 for t in tenants]
    if len(set(digests)) != len(digests):
        raise TenantError(f"{path}: two tenants share a token — that is not isolation")

    roots = {}
    for tenant in tenants:
        root = pathlib.Path(tenant.workspace).expanduser().resolve()
        roots[tenant.id] = root
    for tenant_id, root in roots.items():
        for other_id, other in roots.items():
            if other_id == tenant_id:
                continue
            if root == other or root.is_relative_to(other):
                raise TenantError(
                    f"{path}: workspace of {tenant_id!r} ({root}) is inside or equal "
                    f"to {other_id!r}'s ({other}) — tenant workspaces must be disjoint"
                )
    return tenants


def resolve_tenant(tenants: list[Tenant], token: str) -> Tenant | None:
    """Constant-time token → tenant. Disabled tenants never resolve."""
    if not token:
        return None
    digest = hash_token(token)
    matched = None
    for tenant in tenants:
        # compare_digest on every entry: no early exit, no timing signal
        # about which tenant ids exist.
        if hmac.compare_digest(tenant.token_sha256, digest) and tenant.enabled:
            matched = tenant
    return matched


def tenant_workspace(tenant: Tenant) -> pathlib.Path:
    """The one directory this tenant's requests may touch."""
    root = pathlib.Path(tenant.workspace).expanduser().resolve()
    if not root.is_dir():
        raise TenantError(
            f"tenant {tenant.id!r} workspace {root} does not exist — refusing to "
            "serve a tenant whose workspace would be created implicitly"
        )
    return root


def add_tenant(
    repo_dir: str | pathlib.Path,
    tenant_id: str,
    workspace: str | pathlib.Path,
    *,
    webhook_secret_ref: str = "",
) -> tuple[Tenant, str]:
    """Append a tenant, returning it with its ONE-TIME plaintext token."""
    path = registry_path(repo_dir)
    existing = load_tenants(repo_dir) if path.exists() else []
    token = new_token()
    tenant = Tenant(
        id=tenant_id,
        token_sha256=hash_token(token),
        workspace=str(pathlib.Path(workspace).expanduser().resolve()),
        webhook_secret_ref=webhook_secret_ref,
    )
    payload = {"tenants": [t.model_dump() for t in [*existing, tenant]]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    # Validate what we just wrote: a registry that fails its own rules must
    # not survive the command that created it.
    try:
        load_tenants(repo_dir)
    except TenantError:
        payload = {"tenants": [t.model_dump() for t in existing]}
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        raise
    return tenant, token
