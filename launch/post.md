# One document in, an honest product decision out

I have been building an AI product autopilot: a multi-agent harness that
covers the whole product loop, with a human at every gate that matters.
It builds, tests, and reviews working products from one plain-language
requirements document, English or Chinese, scored by independent
behavioral probes ([benchmark](https://github.com/melodygaoyifan/ai-venture-studio/blob/main/docs/benchmark.md)).
And it finds candidate opportunities from real support tickets and issues,
sizes the market with its own voters attacking the case, writes the PRD
with kill criteria, and reads the outcome cohort honestly
([one real run](https://github.com/melodygaoyifan/ai-venture-studio#a-real-run-unedited)).

You do not have to take any of that on trust, and you should not. The
first step needs no API key: `uvx autoproduct replay --demo` replays a
real review of the repo's own code, offline — including the run where the
pipeline escalated to a human instead of pretending. The numbers are in
the open and typed: the review benchmark reports recall 100%, precision
67% on 13 labeled cases, against bars of 40% and 50% ([reproduce it](https://github.com/melodygaoyifan/ai-venture-studio/blob/main/docs/benchmark.md)).
The outer loop's first live evidence read came back 24.0% (n=250,
CI [0.191, 0.297]) against a 30% kill threshold, and the verdict returned
was insufficient_evidence instead of a win
([the transcript](https://github.com/melodygaoyifan/ai-venture-studio#a-real-run-unedited)).
The benchmark page publishes the failing rows too, because a benchmark you
can only pass is marketing.

The part I trust most is the part that distrusts me: the repo's README is
parsed by its own test suite against its own claim ledger, so if I assert
a number I did not measure, the build fails. This post was written with
the system it announces (created with AI, reviewed and published by a
human), and its own launch PRD carries a kill criterion aimed at the
framework itself: if weekly maintenance costs more attention than it
frees for four straight weeks, scope gets cut — on the record.

Three doors: [solo founders](https://github.com/melodygaoyifan/ai-venture-studio/blob/main/editions/solo/START-HERE.md),
[enterprise](https://github.com/melodygaoyifan/ai-venture-studio/blob/main/editions/enterprise/START-HERE.md),
[engineers](https://github.com/melodygaoyifan/ai-venture-studio/blob/main/editions/engineer/START-HERE.md).
MIT licensed. Try to break the gates — nothing unfixtured registers, and
that claim is falsifiable.
