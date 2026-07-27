# ADR-030 — Multi-tenant server mode (the server half of a reversed non-goal)

- **Status:** accepted, v0.38.0
- **Reverses:** "Multi-tenant SaaS" as out-of-scope (README; doc 18
  ADR-U17 kept enterprise deployability in and multi-tenancy out)
- **Scope of the reversal:** the *server* half only

## Context

`avs serve` fronted exactly one workspace. Anyone running it for
two projects ran two processes on two ports, which is fine for one person
and untenable for an agency or an internal platform team fronting several
repos — the E1 enterprise edition's most common shape.

The original non-goal bundled two separable things:

1. **multi-tenancy** — one process, several isolated workspaces;
2. **SaaS** — accounts, billing, plans, a shared database, a hosted
   control plane, and the operational burden of holding other people's
   source code.

(1) is a routing and isolation problem with a bounded, auditable answer.
(2) changes what this project *is*, and every argument for keeping it out
still holds.

## Decision

Ship (1). One `serve` process may front several tenants, each pinned to
its own workspace directory. Reject (2) — no billing, no plans, no shared
store, no hosted offering, no cross-tenant surface of any kind.

## Mechanism (what keeps it bounded)

- **A tenant is a token and a directory.** `.mas/tenants.yaml` maps an id
  to a SHA-256 token hash and a workspace root. `avs tenant add`
  prints the plaintext token once; only the hash is stored.
- **Workspaces must be disjoint.** Registry loading refuses two tenants
  sharing a root *or one root containing another*. Containment is what
  turns "isolated" into a word instead of a property, so it fails at load
  time rather than at request time.
- **The token picks the workspace, never the client.** No route accepts a
  path, a workspace name, or a tenant id as the thing that grants access.
  The one place an id appears in a URL — `/webhook/github/<tenant_id>` —
  only *selects which HMAC secret must verify the delivery*, because
  GitHub sends no bearer token; the path grants nothing.
- **Per-tenant webhook secrets** are `secret://ENV` references resolved
  through the v0.31 secrets layer. One tenant's secret cannot verify
  another's deliveries, and no secret is written into the registry file.
- **Read routes are scoped too.** `/jobs` and `/reviews` leak PR URLs and
  verdicts; in multi-tenant mode they require the token. Single-tenant
  mode keeps its existing open-read localhost posture, unchanged.
- **Uniform 401s.** Unknown token, disabled tenant, and missing token all
  answer identically, so responses never enumerate tenants. Token
  comparison is constant-time over every entry, with no early exit.
- **`review_id` is validated** against `[A-Za-z0-9_-]{1,64}` before it
  touches a path. It was interpolated into a filesystem path before this
  change; in multi-tenant mode that would have been a traversal into a
  neighbour's workspace, which is how "isolated" fails in practice.

## What stays out

Billing, plans, quotas, a shared database, a hosted control plane,
cross-tenant search, and any per-tenant model-key management. Tenants
bring their own API keys via their own environment, exactly as
single-tenant does — the framework still never holds anyone's keys or
spends anyone's money.

## Consequences

- An agency can front ten client repos from one process, with a per-tenant
  token and a per-tenant GitHub secret.
- Operating multi-tenant mode means holding several parties' source in one
  process's reach. The isolation here is *filesystem and routing* level,
  not OS-level: a Python-level RCE in the harness would cross tenants.
  Anyone whose threat model includes that should still run one process per
  tenant, and the README says so under Honest limits.
- The single-tenant path is untouched, so this reversal costs existing
  users nothing.
