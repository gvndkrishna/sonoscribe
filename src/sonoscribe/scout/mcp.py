"""Local MCP servers as extra task tools. Stdio JSON-RPC, plus simple HTTP."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import threading
import time
from typing import Any, BinaryIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_MCP_TIMEOUT = 8
_NAME_SAFE = re.compile(r"[^a-zA-Z0-9_-]+")


class McpError(RuntimeError):
    pass


def mcp_tool_name(server_id: str, remote: str) -> str:
    sid = _NAME_SAFE.sub("", str(server_id or "").replace("mcp-", "m"))[:10] or "m"
    remote_name = _NAME_SAFE.sub("_", str(remote or "tool"))[:40] or "tool"
    return f"mcp_{sid}_{remote_name}"[:64]


def parse_mcp_name(name: str) -> tuple[str, str] | None:
    text = str(name or "")
    if not text.startswith("mcp_"):
        return None
    parts = text.split("_", 2)
    if len(parts) < 3:
        return None
    return parts[1], parts[2]


def encode_stdio_message(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def read_stdio_message(stream: BinaryIO, deadline: float) -> dict[str, Any]:
    header = b""
    while time.monotonic() < deadline:
        chunk = stream.read(1)
        if not chunk:
            raise McpError("MCP closed.")
        header += chunk
        if header.endswith(b"\r\n\r\n") or header.endswith(b"\n\n"):
            break
        if header.startswith(b"{") and header.endswith(b"\n"):
            try:
                data = json.loads(header.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
            raise McpError("MCP returned invalid JSON.")
    else:
        raise McpError("MCP timed out.")
    length = 0
    text = header.decode("ascii", errors="replace").replace("\r\n", "\n")
    for line in text.strip().split("\n"):
        if line.lower().startswith("content-length:"):
            try:
                length = int(line.split(":", 1)[1].strip())
            except ValueError:
                length = 0
    if length <= 0 or length > 2_000_000:
        raise McpError("MCP returned invalid framing.")
    body = b""
    while len(body) < length:
        if time.monotonic() >= deadline:
            raise McpError("MCP timed out.")
        chunk = stream.read(length - len(body))
        if not chunk:
            raise McpError("MCP closed.")
        body += chunk
    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise McpError("MCP returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise McpError("MCP returned invalid JSON.")
    return data


class McpBundle:
    def __init__(self) -> None:
        self.clients: list[McpClient] = []
        self.specs: list[dict[str, Any]] = []
        self._by_name: dict[str, tuple[McpClient, str]] = {}

    def add(self, client: McpClient) -> None:
        self.clients.append(client)
        auto = bool(client.spec.get("auto"))
        for tool in client.tools:
            name = mcp_tool_name(client.spec.get("id") or "", tool["name"])
            self.specs.append(
                {
                    "name": name,
                    "description": str(tool.get("description") or tool["name"])[:400],
                    "schema": tool.get("schema") if isinstance(tool.get("schema"), dict) else {"type": "object"},
                    "mcp": True,
                    "auto": auto,
                }
            )
            self._by_name[name] = (client, str(tool["name"]))

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        found = self._by_name.get(name)
        if not found:
            raise McpError("Unknown MCP tool.")
        client, remote = found
        return client.call(remote, arguments)

    def close(self) -> None:
        for client in self.clients:
            client.close()
        self.clients = []
        self.specs = []
        self._by_name = {}


class McpClient:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self.tools: list[dict[str, Any]] = []
        self._proc: subprocess.Popen[bytes] | None = None
        self._id = 0
        self._lock = threading.Lock()
        self._url = str(spec.get("url") or "").strip()
        self._http = str(spec.get("transport") or "stdio") == "http"

    def start(self) -> None:
        if self._http:
            if not self._url:
                raise McpError("MCP url is missing.")
        else:
            command = str(self.spec.get("command") or "").strip()
            if not command:
                raise McpError("MCP command is missing.")
            argv = shlex.split(command, posix=True)
            argv.extend(shlex.split(str(self.spec.get("args") or ""), posix=True))
            env = os.environ.copy()
            extra = self.spec.get("env")
            if isinstance(extra, dict):
                for key, value in extra.items():
                    name = str(key).strip()
                    if name:
                        env[name] = str(value)
            self._proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=env,
                bufsize=0,
            )
        self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "sonoscribe", "version": "1.0.0"},
            },
        )
        self._notify("notifications/initialized")
        listed = self._rpc("tools/list", {})
        tools = listed.get("tools") if isinstance(listed, dict) else None
        if not isinstance(tools, list):
            return
        for item in tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            schema = item.get("inputSchema") or item.get("input_schema") or {"type": "object"}
            if not isinstance(schema, dict):
                schema = {"type": "object"}
            self.tools.append(
                {
                    "name": name,
                    "description": str(item.get("description") or name),
                    "schema": schema,
                }
            )
            if len(self.tools) >= 24:
                break

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        data = self._rpc("tools/call", {"name": name, "arguments": arguments if isinstance(arguments, dict) else {}})
        if not isinstance(data, dict):
            return str(data)
        if data.get("isError"):
            raise McpError(_mcp_text(data) or "MCP tool failed.")
        return _mcp_text(data) or "ok"

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass

    def _notify(self, method: str) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if self._http:
            try:
                _http_rpc(self._url, payload)
            except McpError:
                return
            return
        self._send(payload)

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        with self._lock:
            self._id += 1
            ident = self._id
            payload = {"jsonrpc": "2.0", "id": ident, "method": method, "params": params}
            reply = self._roundtrip(payload)
        if not isinstance(reply, dict):
            raise McpError("MCP returned invalid JSON.")
        if reply.get("error"):
            err = reply.get("error")
            message = err.get("message") if isinstance(err, dict) else str(err)
            raise McpError(str(message) or "MCP failed.")
        return reply.get("result")

    def _roundtrip(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._http:
            return _http_rpc(self._url, payload)
        return self._stdio_rpc(payload)

    def _send(self, payload: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            return
        proc.stdin.write(encode_stdio_message(payload))
        proc.stdin.flush()

    def _stdio_rpc(self, payload: dict[str, Any]) -> dict[str, Any]:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise McpError("MCP process is gone.")
        ident = payload.get("id")
        self._send(payload)
        deadline = time.monotonic() + _MCP_TIMEOUT
        while time.monotonic() < deadline:
            data = read_stdio_message(proc.stdout, deadline)
            if data.get("id") == ident:
                return data
        raise McpError("MCP timed out.")


def start_mcp_bundle(servers: list[dict[str, Any]] | None, deadline: float | None = None) -> McpBundle:
    bundle = McpBundle()
    for spec in servers or []:
        if deadline is not None and time.monotonic() > deadline:
            break
        if not isinstance(spec, dict) or spec.get("enabled") is False:
            continue
        client = McpClient(spec)
        try:
            client.start()
        except Exception:
            client.close()
            continue
        if client.tools:
            bundle.add(client)
        else:
            client.close()
    return bundle


def _mcp_text(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in data.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            text = str(item.get("text") or "").strip()
            if text:
                chunks.append(text)
        elif isinstance(item, str) and item.strip():
            chunks.append(item.strip())
    if chunks:
        return "\n".join(chunks)[:8000]
    if data.get("result") not in (None, ""):
        return str(data.get("result"))[:8000]
    return ""


def _http_rpc(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2024-11-05",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=_MCP_TIMEOUT) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:160]
        except Exception:
            detail = ""
        raise McpError(detail or f"MCP HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise McpError("Could not reach that MCP.") from exc
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise McpError("MCP returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise McpError("MCP returned invalid JSON.")
    return data
