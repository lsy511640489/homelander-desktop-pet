from __future__ import annotations

import json
import sys
from typing import Any

from mcp_echo_registry import get_tools
from mcp_echo_tools import current_pnl_tool, daily_news_tool, echo_tool, server_time_tool


def read_message() -> dict[str, Any]:
    header_bytes = bytearray()
    while not header_bytes.endswith(b"\r\n\r\n"):
        chunk = sys.stdin.buffer.read(1)
        if not chunk:
            raise EOFError
        header_bytes.extend(chunk)

    content_length = 0
    for line in header_bytes.decode("ascii", errors="replace").split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())

    if content_length <= 0:
        raise ValueError("missing content length")

    body = sys.stdin.buffer.read(content_length)
    if not body:
        raise EOFError
    return json.loads(body.decode("utf-8"))


def write_message(payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def handle_initialize(request_id: Any) -> None:
    write_message(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "homelander-mcp-echo", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        }
    )


def handle_tools_list(request_id: Any) -> None:
    write_message(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.input_schema,
                    }
                    for tool in get_tools()
                ]
            },
        }
    )


def handle_tools_call(request_id: Any, params: dict[str, Any]) -> None:
    name = params.get("name", "")
    arguments = params.get("arguments") or {}

    if name == "echo":
        result = echo_tool(arguments)
    elif name == "server_time":
        result = server_time_tool(arguments)
    elif name == "current_pnl":
        result = current_pnl_tool(arguments)
    elif name == "daily_news":
        result = daily_news_tool(arguments)
    else:
        write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"unknown tool: {name}"},
            }
        )
        return

    write_message({"jsonrpc": "2.0", "id": request_id, "result": result})


def handle_request(message: dict[str, Any]) -> None:
    method = message.get("method")
    request_id = message.get("id")

    if method == "initialize":
        handle_initialize(request_id)
        return
    if method == "notifications/initialized":
        return
    if method == "tools/list":
        handle_tools_list(request_id)
        return
    if method == "tools/call":
        handle_tools_call(request_id, message.get("params") or {})
        return

    if request_id is not None:
        write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"unknown method: {method}"},
            }
        )


def main() -> int:
    while True:
        try:
            message = read_message()
        except EOFError:
            return 0
        handle_request(message)


if __name__ == "__main__":
    raise SystemExit(main())