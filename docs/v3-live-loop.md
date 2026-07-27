# The v3.0.0 design gate — running one loop to a real decision

The roadmap's remaining bar is not code. It is **one product loop run end
to end, ending in a recorded human kill-or-pivot decision at Gate PL5**
(doc 22 §65). Until that happens the outer loop is machinery that has
never been asked to stop anything, and the README says so under Honest
limits.

`avs loop --root launch` is the instrument for it. It reads the
artifacts the stages already write and reports three criteria:

| | requirement | why it is not satisfiable by code alone |
|---|---|---|
| V3-1 | every in-scope stage has a landed artifact | the stages are automated; this one *is* satisfiable by running them |
| V3-2 | a Gate PL5 evaluation exists, run mechanically | `evaluate_kill_criteria` produces it from the PRD's criteria |
| V3-3 | the PL5 record carries a human kill-or-pivot decision | **a human decides.** No agent may write this field for itself |

## Why the system cannot close its own gate

Three rules in the canon collide to make V3-3 human-only, deliberately:

- **Invariant 14.20** — a fired kill criterion cannot be closed without a
  recorded human decision.
- **ADR-U19** — problem selection, scope-tier lock, and roadmap priority
  are human decisions at PL1/PL2/PL5; the system prepares options and
  never chooses.
- **The claim substrate (§20.53)** — a decision record is a claim like any
  other. Writing "we decided to pivot" with no human behind it is exactly
  the fabricated evidence `synthetic_persona_scan` and `claim_lint` exist
  to stop.

So `loop` will report `design gate not met` forever until a person records
a decision. That is the feature. A framework that could mark its own
kill-or-pivot gate satisfied would have no gate.

## Current state of this repo's cycle

Cycle `autoproduct-launch-1` (declared in `launch/cycle.yaml`) entered at
**P2** — the product existed before the loop was pointed at it, so there
was no opportunity to sense and no market to size before building. That
skip is recorded with its reason rather than left as a silent gap; P0/P1
are in scope for cycle 2, whose candidates come from this cycle's PL5
routing.

V3-1 and V3-2 are met. V3-3 is not. Since v0.51 the PRD carries **two**
axes: the capability criterion (product-bench below its floors for two
consecutive runs) can fire on the next weekly run, and the attention
criterion needs four consecutive weeks of logged
maintenance attention, and the attention log holds one untracked week. A
criterion cannot fire on data that was never collected — and it cannot be
declared safe on it either (`launch/gate-pl5-evaluation.yaml` says exactly
this).

## Closing it, when the data exists

1. Log maintenance attention weekly, once per week, with:

   ```
   avs attention                      # last week's floor + streak state
   avs attention --confirm-hours 5.5 --by <you>
   ```

   The first form measures only what left a timestamp (gate dwell, recorded
   decisions) and states that floor; the second logs *your* number beside it.
   The machine never authors the hours, and the log is append-only. Repeat
   until four consecutive logged weeks exist, or you reach loop 3 —
   whichever comes first. When the criterion fires, the command exits 3 and
   points here.
2. `avs loop --root launch` reports the streak inline — how many
   consecutive over-budget weeks exist, how many remain, and which week to
   log next. Re-run the evaluation mechanically against
   `launch/prd.yaml`'s criteria when it says the criterion has fired.
3. If a criterion fires, `loop` exits **3** and says a decision is due.
   Record it in `launch/gate-pl5-evaluation.yaml`:

   ```yaml
   evaluation:
     human_decision: kill        # kill | pivot | continue
     decided_by: <name>
     decided_at: "<date>"
     rationale: >-
       Why, in your own words. This is the artifact the gate is about.
   ```
4. `kill` or `pivot` closes V3-3 and the v3.0.0 gate. `continue` is a
   legitimate decision but explicitly does **not** close it — the gate is
   about the loop's ability to stop, and a continue proves the opposite.

## What a kill actually looks like here

If the attention criterion fires, the PRD's own remedy is scope cut, not
project death (doc 25 §76.4). The honest options at that gate:

- **kill** a scope area — e.g. stop maintaining a lane whose upkeep is
  eating the attention budget, and record which one.
- **pivot** the loop's target — e.g. move from broad adoption to a single
  edition, with the other doors frozen.
- **continue** and accept the budget overrun, which the ledger will keep
  reporting.

Each is a real decision with a real cost. Picking one is the work the gate
exists to force, and it is yours.
