# ADR-029 — MCP is the real transport for the L0 tool surface

- **Status:** accepted, v0.37.0
- **Supersedes:** the "MCP server partitioning realized in-process by an
  ADR'd mapping" compromise recorded in the doc 23 annotation and carried
  as an open item in the implementation map since v0.8

## Context

Doc 11 §17 makes MCP the internal tool transport for one concrete reason:
**subprocess isolation**. An allowlist keeps a voter from *asking* for a
tool it should not have; a subprocess keeps a bug *inside* a tool it does
have from reaching the harness's memory, file handles, and environment.

The implementation had the allowlist (enforced at the `ToolBox` boundary)
and not the isolation. That was recorded honestly rather than papered
over, but it left the design's stated security property unimplemented
while the map read "in-process by mapping" — a phrasing that could be
mistaken for "done differently" rather than "not done".

## Decision

Ship real MCP servers for the L0 read-only surface, and only that surface:

- `read_only` server — `read_file`, `grep`, `list_files`
- `code_intel` server — `symbol_refs`

Two real partitions rather than eight stubbed ones. The L1/L2 partitions
(`deploy`, `maintenance`, `test_exec`) remain in-process and remain named
as open, because a stub that speaks the protocol without isolating
anything would be the same dishonesty in a new place.

## Mechanism

- JSON-RPC 2.0 over stdio, newline-delimited, one subprocess per server
  per voter invocation, spawned with a list argv and never a shell.
- **The triple check of §17.3, all three layers real:** the skill
  frontmatter allowlist decides which tools exist for a voter; `MCPHost`
  mounts only the servers those tools live in, so an unlisted tool is
  *unreachable* rather than refused; and the server independently refuses
  any tool outside its own partition.
- Watchdog timeouts: a wedged server fails that voter's investigation
  (which then degrades to `BLOCKED_TOOL_FAILURE`) and never hangs a review.
- `.mas/mcp-audit.jsonl` records every call — permitted or refused — with
  voter, server, tool, digested arguments, outcome, and duration. Arguments
  are digested rather than copied so the ledger says what was asked for
  without duplicating searched content into a second place.
- **Opt-in.** `AUTOPRODUCT_TOOL_TRANSPORT=mcp`; in-process stays the
  default because a subprocess spawn per server per invocation is a real
  cost that should be paid deliberately, not by surprise.

## What stays out

**External MCP servers.** Doc 11 §17.1's reasoning is unchanged and, if
anything, stronger: CVE-2025-6514 (mcp-remote RCE) and the unofficial
Postmark server that BCC'd every sent email to its author are what
happens when an agent system trusts someone else's tool process. Every
server here is autoproduct's own code.

## Update (v0.40.0)

The L1/L2 partitions named as open above now ship for the tools that
exist: `deploy` (the deterministic deploy probes), `maintenance`
(recent_commits, correlate), and `test_exec` (run_tests). Each declares a
risk tier and `MCPHost` refuses to mount one above the caller's
`risk_ceiling`, which is the RBAC half of §17.2 rather than only the
partitioning half.

Still open, and still deliberately: the §17.2 table's external-service
tools (`terraform_validate`, `sentry_get_issue`, `datadog_query_metrics`)
are integrations nobody has built. When they arrive they are new tools in
an existing partition — configuration, not architecture.

## Consequences

- The isolation claim in doc 11 §17 is now true for the tools voters
  actually use during code review.
- A path-traversal attempt in `read_file` is refused inside a child
  process; the harness never evaluates the path.
- The map's oldest open item shrank from "the MCP layer" (v0.36) to "the
  L1/L2 partitions" (v0.37) to "external-service integrations nobody has
  built" (v0.40) — each step a smaller and more honest statement.
