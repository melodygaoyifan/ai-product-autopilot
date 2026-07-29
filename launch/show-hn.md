# Show HN: An AI venture studio whose README cannot overclaim

I have been building AI Venture Studio, an open-source multi-agent harness
for the whole product loop, with a human at every gate that matters. It
builds, tests, and reviews working products from one plain-language
requirements document, English or Chinese, scored by independent behavioral
probes ([repo](https://github.com/melodygaoyifan/ai-venture-studio)). And
it finds candidate opportunities from real support tickets and issues,
sizes the market with its own voters attacking the case, writes the PRD
with kill criteria, and reads the outcome cohort honestly.

The part worth your skepticism first: the README is parsed by its own test
suite against its own claim ledger — assert a number that was not measured
and the build fails
([claims/platform.yaml](https://github.com/melodygaoyifan/ai-venture-studio/blob/main/claims/platform.yaml)).
That gate is not decorative. While rewriting the README recently, a
comparison-table cell about neighboring tools tripped the linter on a
single adjective, and CI stayed red until the word was deleted. The same
discipline runs through the product: agents may never author a user quote
or persona, sizing is a range never a point, experiments are hash-pinned
before exposure, and a fired kill criterion cannot be closed without a
recorded human decision.

You do not have to take any of this on trust. With no API key, the demo
replays a real review of the repo's own code offline, including the run
where the pipeline escalated to a human instead of pretending:
`uvx --from ai-venture-studio avs replay --demo`. The review benchmark
reports recall 100%, precision 67% on 13 labeled cases against bars of 40%
and 50% ([method](https://github.com/melodygaoyifan/ai-venture-studio/blob/main/docs/benchmark.md)).
The product benchmark publishes its failures on purpose, because a
benchmark you can only pass is marketing. The worst row is on the record:
product benchmark, real cases run 5 (2026-07-26, n=1, pre-fix baseline):
build 33%, probe pass 0%, clean review 17%
([history](https://github.com/melodygaoyifan/ai-venture-studio/blob/main/benchmarks/results/HISTORY.md)).

Boundaries, stated rather than implied: merges, deploys, publishing, and
spending are gated behind recorded human decisions, and deploy automation
stays disarmed until a human writes an attributed, expiring policy. The
outer loop is honest about its own bar — unproven until a real kill-or-pivot
decision lands on a live cycle — and its launch PRD carries a kill
criterion aimed at the framework itself.

This post was written with the system it announces (created with AI,
reviewed and published by a human). MIT licensed. Try to break the gates —
nothing unfixtured registers, and that claim is falsifiable.
