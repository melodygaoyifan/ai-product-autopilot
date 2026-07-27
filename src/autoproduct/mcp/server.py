"""MCP tool servers — one subprocess per partition (doc 11 §17.2).

    python -m autoproduct.mcp.server read_only --root /path/to/repo

Serves `initialize`, `tools/list`, `tools/call` on stdin/stdout. The
partition table below is the server-side half of the triple check: a
server refuses a tool it does not declare even if the caller asks nicely,
so a host bug cannot widen a voter's reach.

Only the L0 read-only surface is partitioned here. The L1/L2 partitions
(deploy, maintenance, test execution) still run in-process and are named
as open in the implementation map — shipping two real servers beats
stubbing eight.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import IO

from autoproduct.mcp import protocol

# server name → tools it serves (doc 11 §17.2, restricted to the tools
# that exist today in VOTER_TOOL_REGISTRY).
SERVER_TOOLS: dict[str, tuple[str, ...]] = {
    "read_only": ("read_file", "grep", "list_files"),
    "code_intel": ("symbol_refs",),
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
}


def server_for(tool: str) -> str | None:
    """Which partition serves this tool (None if no server does)."""
    for name, tools in SERVER_TOOLS.items():
        if tool in tools:
            return name
    return None


def _handle(
    message: dict, *, server: str, tools: tuple[str, ...], box
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
            text = box.call(name, params.get("arguments") or {})
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
    from autoproduct.tools.voter_tools import ToolBox

    tools = SERVER_TOOLS[server]
    # The subprocess's own budget is unbounded: the *caller's* budget is the
    # contract (enforced host-side, per voter invocation). Bounding it twice
    # with different counters would silently truncate long investigations.
    box = ToolBox(root, allowed=list(tools), budget=10**9)
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
        response = _handle(message, server=server, tools=tools, box=box)
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
