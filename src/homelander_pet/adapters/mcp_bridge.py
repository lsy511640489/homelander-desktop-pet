from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MCPServerSpec:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    enabled: bool = True
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path | None = None


@dataclass(slots=True)
class MCPToolSpec:
    server: str
    name: str
    description: str
    input_schema: dict[str, Any]


class MCPServerSession:
    def __init__(self, spec: MCPServerSpec) -> None:
        self.spec = spec
        self._process: subprocess.Popen[bytes] | None = None
        self._request_id = 0
        self._lock = threading.Lock()
        self._tools: dict[str, MCPToolSpec] = {}

    def _ensure_process(self) -> None:
        if self._process is not None:
            return
        env = os.environ.copy()
        env.update(self.spec.env)
        self._process = subprocess.Popen(
            [self.spec.command, *self.spec.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.spec.cwd,
            env=env,
        )

    def _write_message(self, payload: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("MCP process is not running")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._process.stdin.write(header)
        self._process.stdin.write(body)
        self._process.stdin.flush()

    def _read_message(self) -> dict[str, Any]:
        if self._process is None or self._process.stdout is None:
            raise RuntimeError("MCP process is not running")

        header_bytes = bytearray()
        while not header_bytes.endswith(b"\r\n\r\n"):
            chunk = self._process.stdout.read(1)
            if not chunk:
                stderr_text = ""
                if self._process.stderr is not None:
                    stderr_bytes = self._process.stderr.read()
                    if stderr_bytes:
                        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
                exit_code = self._process.poll()
                detail = f" (exit code {exit_code})" if exit_code is not None else ""
                if stderr_text:
                    raise RuntimeError(f"MCP server closed the stream{detail}: {stderr_text}")
                raise RuntimeError(f"MCP server closed the stream{detail}")
            header_bytes.extend(chunk)

        content_length = 0
        for line in header_bytes.decode("ascii", errors="replace").split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
        if content_length <= 0:
            raise RuntimeError("MCP response missing content length")

        body = self._process.stdout.read(content_length)
        if not body:
            raise RuntimeError("MCP response body missing")
        return json.loads(body.decode("utf-8"))

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            self._ensure_process()
            self._request_id += 1
            request_id = self._request_id
            payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
            if params is not None:
                payload["params"] = params
            self._write_message(payload)

            while True:
                response = self._read_message()
                if response.get("id") == request_id:
                    if "error" in response:
                        raise RuntimeError(str(response["error"]))
                    return response

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._ensure_process()
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._write_message(payload)

    def initialize(self) -> None:
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "homelander-pet", "version": "0.1.0"},
                "capabilities": {},
            },
        )
        self._notify("notifications/initialized")

    def list_tools(self) -> list[MCPToolSpec]:
        response = self._request("tools/list")
        tools_payload = response.get("result", {}).get("tools", [])
        tools: list[MCPToolSpec] = []
        for item in tools_payload:
            tool = MCPToolSpec(
                server=self.spec.name,
                name=item["name"],
                description=item.get("description", ""),
                input_schema=item.get("inputSchema", {"type": "object", "properties": {}, "additionalProperties": True}),
            )
            tools.append(tool)
            self._tools[tool.name] = tool
        return tools

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = self._request("tools/call", {"name": tool_name, "arguments": arguments})
        return response.get("result", {})

    def close(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None


@dataclass(slots=True)
class MCPBridge:
    project_root: Path
    sessions: dict[str, MCPServerSession] = field(default_factory=dict)
    _tool_index: dict[str, tuple[str, str]] = field(default_factory=dict)

    @classmethod
    def from_config(cls, project_root: Path, config_path: Path) -> "MCPBridge":
        resolved_path = config_path if config_path.is_absolute() else project_root / config_path
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        sessions: dict[str, MCPServerSession] = {}
        for item in payload.get("mcp_servers", []):
            if not item.get("enabled", True):
                continue
            spec = MCPServerSpec(
                name=item["name"],
                command=item["command"],
                args=list(item.get("args", [])),
                enabled=True,
                env=dict(item.get("env", {})),
                cwd=project_root,
            )
            session = MCPServerSession(spec)
            session.initialize()
            sessions[spec.name] = session
        return cls(project_root=project_root, sessions=sessions)

    def tool_definitions(self) -> list[dict[str, Any]]:
        definitions: list[dict[str, Any]] = []
        for session in self.sessions.values():
            for tool in session.list_tools():
                tool_name = f"mcp__{tool.server}__{tool.name}"
                self._tool_index[tool_name] = (tool.server, tool.name)
                definitions.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "description": tool.description or f"MCP tool {tool.name} from {tool.server}",
                            "parameters": tool.input_schema,
                        },
                    }
                )
        return definitions

    def invoke(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        mapping = self._tool_index.get(tool_name)
        if mapping is None:
            raise KeyError(f"unknown MCP tool: {tool_name}")
        server_name, real_tool_name = mapping
        session = self.sessions[server_name]
        return session.call_tool(real_tool_name, arguments)

    def close(self) -> None:
        for session in self.sessions.values():
            session.close()
