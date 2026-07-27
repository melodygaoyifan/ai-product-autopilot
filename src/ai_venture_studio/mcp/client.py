"""MCP client — one connected subprocess server (doc 11 §17.3).

Spawns `python -m ai_venture_studio.mcp.server <name> --root <repo>` with a list
argv (never a shell), performs the `initialize` handshake, and exposes
`list_tools` / `call_tool`. Every call carries a timeout: a wedged tool
server must fail the voter's investigation, never hang the review.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from ai_venture_studio.mcp import protocol

DEFAULT_TIMEOUT_S = 30.0


class MCPClientError(RuntimeError):
    pass


class MCPClient:
    def __init__(
        self, server: str, root: str | Path, *, timeout_s: float = DEFAULT_TIMEOUT_S
    ):
        self.server = server
        self.root = str(Path(root).resolve())
        self.timeout_s = timeout_s
        self._proc: subprocess.Popen[str] | None = None
        self._next_id = 0
        self._tools: list[dict] | None = None

    # --- lifecycle ------------------------------------------------------
    def start(self) -> "MCPClient":
        if self._proc is not None:
            return self
        self._proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            [sys.executable, "-m", "ai_venture_studio.mcp.server", self.server,
             "--root", self.root],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, cwd=self.root,
        )
        handshake = self._roundtrip("initialize", {
            "protocolVersion": protocol.PROTOCOL_VERSION,
            "clientInfo": {"name": "autoproduct", "version": "1"},
        })
        if handshake.get("protocolVersion") != protocol.PROTOCOL_VERSION:
            self.close()
            raise MCPClientError(
                f"{self.server}: protocol mismatch — server offered "
                f"{handshake.get('protocolVersion')!r}"
            )
        return self

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin is not None:
                proc.stdin.write(protocol.encode(
                    protocol.request(self._bump(), "shutdown")
                ))
                proc.stdin.flush()
            proc.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait(timeout=5)
        finally:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()

    def __enter__(self) -> "MCPClient":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.close()

    # --- calls ----------------------------------------------------------
    def _bump(self) -> int:
        self._next_id += 1
        return self._next_id

    def _roundtrip(self, method: str, params: dict[str, Any]) -> Any:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise MCPClientError(f"{self.server}: client is not started")
        msg_id = self._bump()
        try:
            proc.stdin.write(protocol.encode(protocol.request(msg_id, method, params)))
            proc.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            raise MCPClientError(f"{self.server}: server exited: {exc}") from exc

        # The server answers one line per request, in order.
        deadline = self.timeout_s
        while True:
            line = _readline_with_timeout(proc, deadline)
            if line is None:
                raise MCPClientError(
                    f"{self.server}: no response to {method!r} within {deadline}s"
                )
            message = protocol.read_message_from_line(line)
            if message.get("id") != msg_id:
                continue  # notification or stale reply: skip
            if "error" in message:
                err = message["error"]
                raise MCPClientError(
                    f"{self.server}: {method} failed "
                    f"[{err.get('code')}] {err.get('message')}"
                )
            return message.get("result")

    def list_tools(self) -> list[dict]:
        if self._tools is None:
            self._tools = list((self._roundtrip("tools/list", {}) or {}).get("tools", []))
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> str:
        payload = self._roundtrip("tools/call", {"name": name, "arguments": arguments})
        blocks = (payload or {}).get("content") or []
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def _readline_with_timeout(proc: subprocess.Popen[str], timeout_s: float) -> str | None:
    """Blocking readline with a wall-clock bound, via a watchdog thread —
    portable across platforms where select() on pipes misbehaves."""
    import threading

    result: list[str] = []

    def _read():
        if proc.stdout is None:
            return
        line = proc.stdout.readline()
        if line:
            result.append(line)

    thread = threading.Thread(target=_read, daemon=True)
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        proc.kill()
        return None
    return result[0] if result else None
