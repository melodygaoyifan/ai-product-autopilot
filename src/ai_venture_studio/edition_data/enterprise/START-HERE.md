# Traditional industry / enterprise — start here

The machinery your governance team will ask about already exists: the
substrate ladder (stages refuse to run vacuously below their
infrastructure floor — `STAGE_INACTIVE`, never theater), Gate R / CAB
evidence bundles, fixture-gated voters, and an attestation ledger. This
edition adds the adoption wrapper — the artifacts a buying organization
needs before the machinery is allowed to run (design doc 24 §69).

## Day 1

```bash
avs init pilot --profile enterprise-web --edition enterprise
avs readiness        # which substrate rung you actually occupy — today
```

The `enterprise-web` profile is `web` plus the constraints your IT and
security review will ask about: append-only audit records on every
state-changing action, `/api/health` for the load balancer, env-only
configuration with `<VAR>_FILE` secret mounts, and versioned JSON
contracts for integration consumers. To evaluate the whole flow with no
key and no egress first: `avs studio pilot --profile enterprise-web
--provider mock`.

`--edition enterprise` sets `require_gate_owner: true`: workspace init
refuses without a named human per gate class. That is the measured profile
of the 12% of enterprise agent pilots that reach production (94% have a
named owner with budget authority; 87% run automated evals on every
change) — enforced at init, not recommended in a slide.

## Your forge, your network, your model door

Reviews target GitLab MR URLs (self-managed hosts and subgroups included,
via `glab`) as first-class citizens next to GitHub PRs — comments, HITL
issues, fix-MRs, webhooks, and policy-gated merges all follow the
target's forge, and `avs review --from-ci` runs inside a merge-request
pipeline when the perimeter cannot expose a webhook endpoint at all.
If the network path to Anthropic is AWS, GCP, or Azure rather than the
public API, set `AVS_ANTHROPIC_MODE=bedrock|vertex|foundry`; an internal
LLM gateway works via `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL`;
keys can arrive as K8s secret mounts (`*_FILE`). The complete
outbound-host allowlist for your network team is
[procurement/network-egress.md](procurement/network-egress.md); the env
tables are in [RUNBOOK.md § Enterprise environments](../../RUNBOOK.md#enterprise-environments-gitlab-bedrockvertexfoundry-gateways-air-gap).

## Before the security questionnaire arrives

Hand over [procurement/](procurement/) — the data-flow one-pager (what
leaves the machine and what never does), the sandbox-tier map, and a
sample Gate-R evidence bundle. The answers exist before the questions.

## Before the pilot starts

Fill in [procurement/pilot-to-production.md](procurement/pilot-to-production.md):
graduation criteria authored **as kill criteria** at pilot start — named
owner, target outcome, loop budget, evaluation cadence. A pilot without
them is the 88% that fade out; with them, non-graduation is a recorded
Gate PL5 decision instead of a fade-out.

## Compliance posture

EU AI Act Art. 50 transparency duties apply from 2026-08-02; your
organization is the **deployer** for Art. 50(4) disclosures. The shipped
compliance profile carries `verified_on` fields your counsel confirms —
the check fails closed when the ruleset expires (design doc 21 §58.2).

Read next: design docs 18–19 (the substrate ladder and Gate R are your
spine), then day-0-calibration before any week-level commitment.
