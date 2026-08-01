# ADR-032 — No framework-side spending cap; spend is measured, never gated

- **Status:** accepted, 2026-08-01 (operator decision)
- **Reverses:** the monthly spending cap shipped in v0.65.0 (`avs prices
  --cap`, `cost_gate` refusals at Gate 1 and per build task) and its Studio
  ceiling form shipped in v0.66.0
- **Does not reverse:** spend metering (the ledger, `avs cost`, the build
  report's cost line, the Studio cost card), the sourced reference price
  table (`avs prices`), or ADR-U20 ("the framework never spends money")

## Context

v0.65.0 gave the cost gate teeth (sourced list prices, a monthly
`monthly_cap_usd`, refusals at Gate 1 and between build tasks) and v0.66.0
put a one-click ceiling form in the founder Studio, motivated by published
research on runaway usage-billed sessions. Both were opt-in and honestly
worded. Neither was wrong on its own terms.

The operator's decision reverses them on a cleaner principle: **every model
call is billed to the operator's own key or subscription, so budget
enforcement belongs to the provider account that does the billing.**
Anthropic, OpenAI, and Google all offer spending limits at the account
level, and those limits are *authoritative* — they see all usage on the
key, not just this framework's slice, and they cannot be bypassed by a bug
here. A framework-side cap is at best a duplicate of that control and at
worst a contradiction of it: for subscription billing (flat-rate plans),
tokens do not map to marginal dollars at all, so a token-priced dollar cap
would pause builds over money that was never being spent.

There is also a consistency argument with the system's own posture. The
framework never holds keys and never spends money on its own (ADR-U20); a
mechanism that *refuses the operator's own instructions* over the
operator's own money inverts that relationship. The gate's refusal message
already had to strain to attribute the stop to the operator ("the limit
YOU set") — a sign the mechanism sat on the wrong side of the boundary.

## Decision

1. **No spending cap exists anywhere in the framework.** `cost_gate`,
   `monthly_cap_usd`, `cap_check`, the `--cap` flag, and the Studio ceiling
   form are removed. Nothing in any pipeline refuses work over money.
2. **Spend visibility stays, and is the product's answer to cost fear.**
   The ledger meters every call at the adapter; the build report ends with
   what the run cost, as arithmetic; `avs cost` prints the month per model;
   the Studio card shows spend on the confirm page (before the first
   dollar) and the report page. An unpriced call keeps the total labelled a
   FLOOR — never counted as zero.
3. **The reference price table stays, as estimation only.** Sourced,
   dated, ranges resolved upward, operator corrections surviving re-import
   — feeding `avs cost` and the report, gating nothing.
4. **Budget enforcement is documented as the provider's job.** The README
   and `avs cost` point at provider-side spending limits, which is where a
   ceiling is both effective and complete.

## What keeps this honest

An old `cost-model.yaml` carrying `monthly_cap_usd` still loads — the key
is ignored, never an error — so no workspace breaks on upgrade. The
removal is pinned by tests as firmly as the presence was: a month of heavy
spend must not stop a build (`test_a_build_never_refuses_over_money`), the
review gate must pass regardless of spend, and the Studio card must render
no ceiling form and no refusal copy.

A reversal recorded only in a commit message would be indistinguishable
from scope drift, which is why this document exists (§10 Part 11: the
newest accepted decision wins and must be recorded).
