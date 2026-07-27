"""MCP transport for voter tools (doc 11 §17).

Through v0.36 the docs' MCP layer was realized in-process "by an ADR'd
mapping" — the allowlist and budget were enforced at the `ToolBox`
boundary, in the harness process. That bought the contract but not the
property the design wanted from MCP: **subprocess isolation**, so a path
traversal bug in `read_file` is bounded by a child process's filesystem
access rather than the harness's.

This package ships the real transport for the read-only tool surface:

- `protocol` — JSON-RPC 2.0 framing over stdio (newline-delimited).
- `server`  — `python -m autoproduct.mcp.server <name>`: one subprocess per
  server, serving `initialize`, `tools/list`, `tools/call`, exposing only
  the tools its partition declares.
- `client`  — spawns and talks to one server; timeouts, no shell.
- `host`    — mounts only the servers a voter's allowlist needs, enforces
  the triple check (spec → host → server), and appends every call to
  `.mas/mcp-audit.jsonl`.
- `toolbox` — `MCPToolBox`, drop-in for `ToolBox`, so the transport is a
  switch (`AUTOPRODUCT_TOOL_TRANSPORT=mcp`) rather than a rewrite.

Scope, deliberately: these servers are autoproduct's own code and speak
MCP *internally only*. External MCP servers stay out (doc 11 §17.1 cites
CVE-2025-6514 and the Postmark BCC incident); the L2 test-execution and
L1 deploy/maintenance partitions stay in-process for now, named in the
implementation map rather than half-built here.
"""

from autoproduct.mcp.host import MCPHost, MCPPermissionError
from autoproduct.mcp.toolbox import MCPToolBox, tool_transport

__all__ = ["MCPHost", "MCPPermissionError", "MCPToolBox", "tool_transport"]
