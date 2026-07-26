# The weekly founder review (30–45 minutes, in this order)

> Consolidation is scheduling, never deletion (ADR-U27). Everything below
> already has its full record; this ritual is where the one human spends
> attention deliberately instead of continuously.

## 1. Kill criteria — first, while attention is fresh (10 min)

- `autoproduct` cycle report: any **fired** criterion has already
  interrupted your week (it is never batchable — invariant 14.20). Here
  you review the *near-threshold* ones: what reading would fire them, and
  is next week's plan raising or lowering that chance?
- Revising a criterion requires **new criteria and new evidence** — a
  re-reading of old data is the zombie signature (F-22.3).

## 2. The batched gate queue (15 min)

- Gate 2 plan confirmations (`risk: low` only) · Gate PL3 publish
  approvals · trust-tier promotions · compounding-loop CLAUDE.md
  proposals · cadence/WIP tuning.
- **Blocking exit criterion:** run `autoproduct dwell`. Fast acks + zero
  overrides is the rubber-stamp pattern (F-24.1) — if it flags, slow down
  and actually read one item end-to-end before closing the review.
- Never in this queue: PL5 decisions, incident triage, anything touching
  auth/payment/user data at Gate 3, consent/suppression overrides (none
  exist — §21.58.3).

## 3. The sweep digest (5 min)

- Read this week's `.mas/sweep/digest-*.yaml`: what was patched (within the
  `max_open_prs: 1` cap), what was reported, and the action rate. A clean
  pass is a record, not silence — an unchanged snapshot hash across weeks
  while debt metrics grow contradicts itself (F-29.5).
- Rung promotions (SW0 → SW1 → SW2) are YOUR recorded decision, made here.

## 4. The attention ledger (10 min)

- Hours spent this week vs. `attention cost per resolved hypothesis`
  (§22.66.4). If the trend is wrong, the honest fix is fewer artifacts and
  fewer open loops — not faster approvals.

## 5. Next week's WIP (5 min)

- One product bet (`wip: 1`). Name what the loser gets: parked with a
  `revisit_if`, or killed with its learning recorded.

## Monthly self-audit prompt (append to the fourth review)

Did any batched item this month deserve an interrupt? If yes, move its
class out of the batch. Did you override *anything*? If no — that is not
evidence the machine is right; it is F-24.1's precondition.
