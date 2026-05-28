from __future__ import annotations

from mcp_echo_decorator import TOOL_HANDLERS


def get_tools() -> list:
	return [handler.definition for handler in TOOL_HANDLERS]