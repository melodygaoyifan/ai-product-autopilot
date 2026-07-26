# Traditional industry / enterprise — start here

The machinery your governance team will ask about already exists: the
substrate ladder (stages refuse to run vacuously below their
infrastructure floor — `STAGE_INACTIVE`, never theater), Gate R / CAB
evidence bundles, fixture-gated voters, and an attestation ledger. This
edition adds the adoption wrapper — the artifacts a buying organization
needs before the machinery is allowed to run (design doc 24 §69).

## Day 1

```bash
autoproduct init pilot --profile web --edition enterprise
autoproduct readiness        # which substrate rung you actually occupy — today
```

`--edition enterprise` sets `require_gate_owner: true`: workspace init
refuses without a named human per gate class. That is the measured profile
of the 12% of enterprise agent pilots that reach production (94% have a
named owner with budget authority; 87% run automated evals on every
change) — enforced at init, not recommended in a slide.

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
