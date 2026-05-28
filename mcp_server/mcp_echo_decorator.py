from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(slots=True)
class ToolHandler:
    definition: ToolDefinition
    handler: Callable[[dict[str, Any]], dict[str, Any]]


TOOL_HANDLERS: list[ToolHandler] = []


def mcp_tool(
    name: str,
    *,
    description: str,
    input_schema: dict[str, Any],
) -> Callable[[Callable[[dict[str, Any]], dict[str, Any]]], Callable[[dict[str, Any]], dict[str, Any]]]:
    def decorator(function: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
        TOOL_HANDLERS.append(
            ToolHandler(
                definition=ToolDefinition(name=name, description=description, input_schema=input_schema),
                handler=function,
            )
        )
        return function

    return decorator