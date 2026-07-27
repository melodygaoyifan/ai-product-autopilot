# Data flow one-pager (for the security questionnaire)

## What leaves the machine

**Model API calls only** — prompts and completions to the LLM providers
you configure (`ANTHROPIC_API_KEY` required; OpenAI/Gemini/xAI optional
voter seats). Keys live in your environment; they are never written to
the workspace, to git, or into any prompt (credential vault, design
§21.57). If a provider key is absent, the seat fails loudly or visibly
substitutes — never silently.

**Telemetry: nothing, by default.** Opt-in only (`avs telemetry
on`), aggregate-only and schema-pinned — version, edition, substrate rung,
stage/gate outcome counts, error classes. Never: FDR content, code,
prompts, model outputs, repo names, claims. `avs telemetry show`
prints the exact next payload before anything would send (ADR-U28).

## What never leaves

- **Person-level data** — cannot leave the analytics boundary even
  internally: the query layer refuses person-level rows, applies a
  k-anonymity floor (≥25, raisable only), and PII-redacts free text
  (invariant 14.16, `user_data_taint`).
- **Your code and data** — processed locally; review/test sandboxes are
  tiered (T1 subprocess → T3 network-disconnected container, design
  §11.17); the T3 fallback path is visible in every report.
- **Money** — the framework has no spend capability of any kind (ADR-U20).
- **Publishing** — no external post, send, or public-property change
  without a scoped, per-artifact human approval (§21.57.2).

## Audit surface

Every gate decision, automated approval, and voter verdict lands in the
YAML mirror (`.mas/reviews/…`, replayable offline) and the hash-chained
attestation ledger (`avs attest`); Gate-R evidence bundles export
per review (`avs evidence-bundle`). Records are edition-invariant
(invariant 14.22) — batched approvals log identically to unbatched ones.

Cross-references: `SECURITY.md` (design repo) for the OWASP LLM Top 10
mapping; design doc 18 §49 for the attestation ledger; doc 22 §64 for the
taint classes this pager summarizes.
