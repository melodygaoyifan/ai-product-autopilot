# Pilot-to-production contract (fill in at pilot START, not at review time)

> Graduation criteria are authored as kill criteria (§20.56.2) before
> anyone is attached to the pilot. A pilot without them is the 88% that
> never reach production; with them, non-graduation is a recorded Gate PL5
> decision instead of a fade-out.

## 1. Ownership (the 12% profile, §69.1)

- Named owner with budget authority: ______________________
- Named human per gate class (init enforces `require_gate_owner`):
  - Gate 2 (plan): ______  · Gate 3 (verdict): ______
  - Gate R (CAB): ______  · Gate PL5 (portfolio): ______

## 2. Target outcome (one, measurable)

- Metric (must have a definition file in `metrics/`): ______________
- Baseline (value, source, n): ______________
- Target (value, by-date): ______________
- Instrumentation event (exists, or is a named task before launch): ______

## 3. Graduation / kill criteria (mechanically evaluated)

- GRADUATE when: outcome ≥ ______ for ______ consecutive loops.
- KILL/PIVOT review fires when: outcome achieves < 50% of target lift
  after `after_loops:` ______ loops, **or** loop budget `max_loops:` ______
  exhausts — whichever comes first. Neither can be closed without a
  recorded human decision (invariant 14.20).

## 4. Evaluation cadence

- `autoproduct eval-gate` on every change (the 87% profile): yes / yes.
- Weekly: gate-latency + approval-dwell distribution (`autoproduct dwell`).
- Per loop: cycle report with `attention_spent` reviewed at Gate PL5.

## 5. Scope honesty

- Substrate rung at start (`autoproduct readiness`): ______
- Stages inactive at that rung (listed, not hidden): ______________
- What this pilot does NOT claim: headcount replacement; autonomous
  deploys; coverage of stacks without a calibrated det-tools lane
  (PROVISIONAL rule, design doc 19).

Signed (owner): ______________  Date: ________  Review date: ________
