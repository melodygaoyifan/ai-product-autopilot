---
metric:
  id: product_bench_build_rate
  definition: "fraction of product-bench cases whose generated product BUILDS (every planned task reaching built with its suite green) in one run; companion series in the same run are the probe pass rate and the clean-review rate"
  numerator_event: product_bench.case_built
  denominator: "cases in the run's corpus (benchmarks/products-real/)"
  window_days: 7
  cohort_basis: bench_run
  exclusions: ["cases that died on harness noise rather than on the product under test (run 4 KeyError, run 5 budget exhaustion)", "runs whose corpus differs — comparability resets when a case is added or edited"]
  owner: melody
  changed_at: "2026-07-27"
---

# product-bench capability (build / probes / clean)

## Why this is a kill-criterion axis

The attention axis (`weekly_maintenance_attention.md`) asks whether the
framework is affordable to keep. This one asks the prior question: **does it
still work?** A build rate that collapses means the product loop is
generating things that do not run, and no amount of attention discipline
makes that worth continuing.

Its practical advantage as a second axis is that **the series already
exists**. `benchmarks/results/HISTORY.md` carries runs 4–11 with a result
YAML per run, and the cadence is now weekly. The attention axis cannot fire
until four consecutive weeks are logged; this one can fire on the next run.

## The observed distribution (what makes the floors real)

| era | build | probes | clean |
|---|---|---|---|
| runs 4–5 (pre-fix) | 8–33% | 0% | 0–17% |
| runs 6–9 (fixes landing) | 42–72% | 23–90% | 0–41% |
| runs 10–11 (current) | 74–75% | 75% | 38–43% |

The kill criterion's 60% build / 50% probe floors sit **below the current
level and above the pre-fix era**. They are read off this table, not chosen
to be comfortable: crossing them means the system has regressed into
territory it has already climbed out of once.

## How it is evaluated

`avs bench-criterion` reads the tracked result YAMLs, takes the two
most recent comparable runs, and reports whether the criterion has fired. It
never rewrites history and never averages across a corpus change. A fired
criterion demands a recorded human decision at Gate PL5 (invariant 14.20) —
the evaluator states, it does not decide.

## Falsifier

Two consecutive weekly runs at or above 60% build and 50% probes falsify the
regression claim for that window. A single good run does not: the whole point
of "2 consecutive" is that one lucky run is noise at this corpus size (n=4
real-product cases).
