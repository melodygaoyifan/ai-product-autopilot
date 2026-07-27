# Architecture Decision Records

The design canon (docs 08–29) carries ADR-001…ADR-U37 inline. This
directory holds the records made *in the implementation* after the canon
was written — most importantly the ones that **reverse a previously
recorded non-goal**, because a scope reversal that lives only in a commit
message is indistinguishable from scope creep.

The change-control protocol (§10 Part 11) applies: the newest accepted
decision wins and must be recorded. These files are that record.

| ADR | Decision | Reverses |
|---|---|---|
| [029](029-mcp-transport-partial.md) | MCP is the real transport for the L0 read-only tool surface; L1/L2 stay in-process | narrows the "in-process by ADR'd mapping" compromise |
| [030](030-multi-tenant-server.md) | One `serve` process may front several isolated workspaces | "Multi-tenant SaaS" (README out-of-scope) — the server half only |
| [031](031-policy-armed-automation.md) | Merge and deploy execution become possible, but only when a human arms a policy file | "Auto-merge to main. Auto-deploy to production." (README out-of-scope, §08.1.8) |

## Format

Each record states: context, the decision, what it reverses and why that
reversal is defensible, what stays out, and the mechanism that keeps the
new capability bounded. A record without a *mechanism* section is an
opinion, not a decision.
