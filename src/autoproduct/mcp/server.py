"""MCP tool servers — one subprocess per partition (doc 11 §17.2).

    python -m autoproduct.mcp.server read_only --root /path/to/repo

Serves `initialize`, `tools/list`, `tools/call` on stdin/stdout. The
partition table below is the server-side half of the triple check: a
server refuses a tool it does not declare even if the caller asks nicely,
so a host bug cannot widen a voter's reach.

Five partitions ship: the two L0 read-only ones (v0.37) and the L1/L2
stage servers (v0.40) whose tools exist — deploy probes, maintenance
correlation, and test execution. Each declares a risk tier, and the host
refuses to mount one above the caller's ceiling.

`sentry_get_issue` (v0.43) is the first external-service tool, and adding
it needed only a row in this table plus a reader module — no transport,
host, or RBAC change. The remaining §17.2 integrations
(`terraform_validate`, `datadog_query_metrics`, …) stay named as open rather
than stubbed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import IO

from autoproduct.mcp import protocol

# server name → tools it serves (doc 11 §17.2). L0 partitions serve the
# voter tool registry; L1/L2 partitions serve the stage tools in
# mcp/stage_tools.py. The §17.2 external-service tools that remain unbuilt
# (terraform_validate, datadog_query_metrics, …) stay named as open in the
# implementation map rather than stubbed here.
SERVER_TOOLS: dict[str, tuple[str, ...]] = {
    "read_only": ("read_file", "grep", "list_files"),
    "code_intel": ("symbol_refs",),
    "deploy": ("migration_scan", "workflow_scan", "canary_scan"),
    "maintenance": ("recent_commits", "correlate", "sentry_get_issue"),
    "test_exec": ("run_tests",),
}

# Risk tier per server (§17.2). The host refuses to mount a server above the
# caller's declared ceiling, so a read-only voter cannot reach L1/L2 even if
# a future skill names one of their tools.
SERVER_RISK: dict[str, int] = {
    "read_only": 0,
    "code_intel": 0,
    "deploy": 1,
    "maintenance": 1,
    "test_exec": 2,
}

TOOL_SCHEMAS: dict[str, dict] = {
    "read_file": {
        "description": "Read a window of one repo file, line-numbered.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            "required": ["path"],
        },
    },
    "grep": {
        "description": "Regex search across repo files matching a glob.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "glob": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["pattern"],
        },
    },
    "list_files": {
        "description": "List repo files matching a glob.",
        "inputSchema": {
            "type": "object",
            "properties": {"glob": {"type": "string"}},
        },
    },
    "symbol_refs": {
        "description": "Find definitions and references of a symbol.",
        "inputSchema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    "migration_scan": {
        "description": "Scan a diff for destructive or unguarded migrations.",
        "inputSchema": {
            "type": "object",
            "properties": {"diff_text": {"type": "string"}},
            "required": ["diff_text"],
        },
    },
    "workflow_scan": {
        "description": "Scan a diff for unsafe CI workflow configuration.",
        "inputSchema": {
            "type": "object",
            "properties": {"diff_text": {"type": "string"}},
            "required": ["diff_text"],
        },
    },
    "canary_scan": {
        "description": "Scan a diff for canary/rollout policy problems.",
        "inputSchema": {
            "type": "object",
            "properties": {"diff_text": {"type": "string"}},
            "required": ["diff_text"],
        },
    },
    "recent_commits": {
        "description": "Recent commits with touched files, for correlation.",
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer"},
                           "limit": {"type": "integer"}},
        },
    },
    "correlate": {
        "description": "Rank recent commits by overlap with an incident text.",
        "inputSchema": {
            "type": "object",
            "properties": {"incident_text": {"type": "string"},
                           "days": {"type": "integer"}},
            "required": ["incident_text"],
        },
    },
    "sentry_get_issue": {
        "description": "Read one Sentry issue (read-only; payload is wrapped "
                       "as untrusted research).",
        "inputSchema": {
            "type": "object",
            "properties": {"issue_id": {"type": "string"}},
            "required": ["issue_id"],
        },
    },
    "run_tests": {
        "description": "Run the repository's test gate (EXECUTES repo code).",
        "inputSchema": {
            "type": "object",
            "properties": {"diff_text": {"type": "string"},
                           "mode": {"type": "string"}},
        },
    },
}


def server_for(tool: str) -> str | None:
    """Which partition serves this tool (None if no server does)."""
    for name, tools in SERVER_TOOLS.items():
        if tool in tools:
            return name
    return None


def _handle(
    message: dict, *, server: str, tools: tuple[str, ...], box, root: str | Path = "."
) -> dict | None:
    method = message.get("method")
    msg_id = message.get("id")
    if method == "initialize":
        return protocol.result(msg_id, {
            "protocolVersion": protocol.PROTOCOL_VERSION,
            "serverInfo": {"name": f"autoproduct.{server}", "version": "1"},
            "capabilities": {"tools": {}},
        })
    if method in ("notifications/initialized", "initialized"):
        return None  # notification: no response
    if method == "tools/list":
        return protocol.result(msg_id, {
            "tools": [
                {"name": name, **TOOL_SCHEMAS[name]}
                for name in tools
                if name in TOOL_SCHEMAS
            ]
        })
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        if name not in tools:
            # The server-side half of the triple check.
            return protocol.error(
                msg_id, protocol.TOOL_NOT_PERMITTED,
                f"server {server!r} does not serve tool {name!r} "
                f"(it serves {list(tools)})",
            )
        try:
            arguments = params.get("arguments") or {}
            if box is not None:
                text = box.call(name, arguments)
            else:
                from autoproduct.mcp.stage_tools import call_stage_tool

                text = call_stage_tool(name, root, arguments)
        except Exception as exc:  # noqa: BLE001 — errors travel as protocol data
            return protocol.error(
                msg_id, protocol.INTERNAL_ERROR, f"{type(exc).__name__}: {exc}"
            )
        return protocol.result(msg_id, {
            "content": [{"type": "text", "text": text}],
            "isError": text.startswith("error:"),
        })
    if method == "shutdown":
        return protocol.result(msg_id, {})
    return protocol.error(msg_id, protocol.METHOD_NOT_FOUND, f"unknown method {method!r}")


def serve(
    server: str, root: str | Path, stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
) -> None:
    """Run one server's request loop until EOF or `shutdown`."""
    if server not in SERVER_TOOLS:
        raise SystemExit(
            f"unknown server {server!r}; known: {sorted(SERVER_TOOLS)}"
        )
    from autoproduct.tools.voter_tools import VOTER_TOOL_REGISTRY, ToolBox

    tools = SERVER_TOOLS[server]
    # L0 partitions serve registry tools through the ToolBox (path scoping,
    # size caps); L1/L2 partitions dispatch to stage_tools. The subprocess's
    # own budget is unbounded: the *caller's* budget is the contract
    # (enforced host-side, per invocation). Bounding it twice with different
    # counters would silently truncate long investigations.
    box = (
        ToolBox(root, allowed=list(tools), budget=10**9)
        if set(tools) <= VOTER_TOOL_REGISTRY
        else None
    )
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    while True:
        try:
            message = protocol.read_message(stdin)
        except protocol.ProtocolError as exc:
            protocol.write_message(
                stdout, protocol.error(None, protocol.PARSE_ERROR, str(exc))
            )
            continue
        if message is None:
            return
        response = _handle(message, server=server, tools=tools, box=box, root=root)
        if response is not None:
            protocol.write_message(stdout, response)
        if message.get("method") == "shutdown":
            return


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="autoproduct.mcp.server")
    parser.add_argument("server", choices=sorted(SERVER_TOOLS))
    parser.add_argument("--root", default=".", help="Repository root to serve")
    args = parser.parse_args(argv)
    serve(args.server, args.root)


if __name__ == "__main__":  # pragma: no cover — subprocess entry point
    main()
