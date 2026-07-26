# Product-bench history

The scoreboard across the real-product bench runs. On 2026-07-26 the
canonical gitignored `.mas/product-bench/` was deleted mid-session and runs
1–8's original result files were lost; this directory is the durable,
git-tracked record (and `save_summary` now writes every new result here
automatically). Files marked *reconstructed* were rebuilt from complete or
partial copies held in the working session; the table below is authoritative
for the headline numbers.

| Run | Result file | Code | Build | Probes | Clean | Notes |
|----|----|----|----|----|----|----|
| 1 | result-2026-07-23-0507 (lost) | pre-fixes | — | — | — | numbers not preserved |
| 2 | result-2026-07-24-0507 (lost) | pre-fixes | 14% | 0% | 50% | 2 cases only; write-lock instant-fatal era |
| 3 | result-2026-07-24-0700 (lost) | pre-2ac1bd4 | 18.5% | 0% | 11% | skeleton-reword deaths dominated |
| 4 | …0259, reconstructed (full) | 991c28c⁻ | 8% | 0% | 0% | infra noise: 2 cases crashed (KeyError new_content; brief YAML budget) |
| 5 | …0524, reconstructed (full) | pre-8b422a3 | 33% | 0% | 17% | case 04 built 6/6, all probes dead: no boot contract + spec drift |
| 6 | result-2026-07-26-0706 (lost) | 8b422a3 | 72.4% | 23.3% | 41.2% | boot gate + scope law proven; remaining failures all contract-drift shaped |
| 7 | …0844, reconstructed (partial) | 2f323e9 | 42% | 90% | 0% | both contract fixes land; whole-surface-in-one-task appears |
| 8 | result-2026-07-26-2152 (lost) | 2bb4808 | 44% | 75% | 0% | flat; case 01 cross-iteration phantom-import signature |
| 9 | result-2026-07-26-2320.yaml (original) | 043176b | 54% | 75% | 8% | case 01 perfect + first clean review; case 03 probegen produced 0 probes |

Fix lineage: 991c28c (bench crash fixes) → 8b422a3 (scope law, boot gate,
workspace hygiene) → 972a680 (spec gets the FDR verbatim) → 9ea8769 (bench
single-instance lock) → 2f323e9 (implementer gets the FDR; no-crash rule) →
2bb4808 (additive-only fixtures, tests-only close, error bodies) → 3b327ab
(private names exempt; stale-import feedback) → this commit (fixture
visibility in the implementer prompt, probegen retry + unmeasured-case
visibility, SSRF probe scoped to non-test code, results dual-written here).
