"""JSON-RPC 2.0 over stdio — the wire format, and nothing else.

Newline-delimited JSON rather than LSP-style `Content-Length` headers:
both are used in the wild for MCP stdio, and one line per message keeps
the transport debuggable by `cat`-ing a captured stream, which matters
more here than framing exotica. Every message is a single line of UTF-8
JSON; embedded newlines are escaped by the encoder.
"""

from __future__ import annotations

import json
from typing import IO, Any

PROTOCOL_VERSION = "2026-03-26"

# JSON-RPC error codes (the subset this transport uses).
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
# Server-defined: the tool exists but this server does not serve it.
TOOL_NOT_PERMITTED = -32001


class ProtocolError(RuntimeError):
    pass


def encode(message: dict[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"


def write_message(stream: IO[str], message: dict[str, Any]) -> None:
    stream.write(encode(message))
    stream.flush()


def read_message_from_line(line: str) -> dict[str, Any]:
    """Parse one wire line into a message object."""
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"malformed JSON-RPC line: {exc}") from exc
    if not isinstance(message, dict):
        raise ProtocolError(f"JSON-RPC message must be an object, got {type(message)}")
    return message


def read_message(stream: IO[str]) -> dict[str, Any] | None:
    """Next message, or None at clean EOF. Blank lines are skipped."""
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if line:
            return read_message_from_line(line)


def request(msg_id: int, method: str, params: dict[str, Any] | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}


def result(msg_id: Any, payload: Any) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": payload}


def error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
