from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp_echo_decorator import mcp_tool


_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if _SRC_DIR.exists():
    src_path = str(_SRC_DIR)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

from homelander_pet.adapters.news_digest import NewsDigestTracker
from homelander_pet.adapters.stock_tracker import StockTrendTracker

@mcp_tool(
    name="echo",
    description="Echo the input text back to the caller.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to echo back."},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
)
def echo_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    text = str(arguments.get("text", ""))
    return {"content": [{"type": "text", "text": text}]}


@mcp_tool(
    name="server_time",
    description="Return the current UTC time in ISO 8601 format.",
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
)
def server_time_tool(_arguments: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": datetime.now(tz=UTC).isoformat()}]}


@mcp_tool(
    name="current_pnl",
    description="Calculate the overall daily profit and loss for configured stock positions in RMB using live quotes.",
    input_schema={
        "type": "object",
        "properties": {
            "timeout_seconds": {
                "type": "number",
                "description": "Quote fetch timeout in seconds.",
                "minimum": 1,
            },
        },
        "additionalProperties": False,
    },
)
def current_pnl_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    timeout_seconds = _coerce_timeout_seconds(arguments.get("timeout_seconds"))
    tracker = StockTrendTracker.from_environment()
    if tracker is None:
        raise ValueError(
            "no stock positions were configured; set HOMELANDER_PET_STOCK_CODES="
            "symbol:shares entries such as 513010:5800,518600:500"
        )
    tracker.timeout_seconds = timeout_seconds
    snapshot = tracker.daily_pnl_snapshot()

    lines = [
        "currency=CNY",
        f"daily_pnl_cny={_format_cny(snapshot.net_pnl)}",
        f"daily_pnl_percent={_format_signed(snapshot.net_pnl_percent)}%",
        f"market_value_cny={_format_cny(snapshot.market_value)}",
        f"previous_close_value_cny={_format_cny(snapshot.previous_close_value)}",
    ]

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@mcp_tool(
    name="daily_news",
    description="Collect and search today's hot news from configured RSS/Atom feeds in Chinese or English.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional keyword or topic to filter the daily digest.",
            },
            "limit": {
                "type": "number",
                "description": "Maximum number of news items to return.",
                "minimum": 1,
                "maximum": 50,
            },
            "timeout_seconds": {
                "type": "number",
                "description": "Feed fetch timeout in seconds.",
                "minimum": 1,
            },
        },
        "additionalProperties": False,
    },
)
def daily_news_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    tracker = NewsDigestTracker.from_environment()
    timeout_seconds = _coerce_timeout_seconds(arguments.get("timeout_seconds"))
    tracker.timeout_seconds = timeout_seconds
    query = _coerce_text(arguments.get("query"))
    limit = _coerce_positive_int(arguments.get("limit"))
    snapshot = tracker.daily_digest(query=query, limit=limit)

    lines = [
        f"date={snapshot.generated_at.date().isoformat()}",
        f"sources={snapshot.source_count}",
        f"items={len(snapshot.items)}",
    ]
    if snapshot.query:
        lines.append(f"query={snapshot.query}")
    for index, item in enumerate(snapshot.items, start=1):
        time_text = item.published_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC") if item.published_at else "unknown"
        lines.append(
            " | ".join(
                [
                    f"{index}. {item.title}",
                    f"source={item.source}",
                    f"time={time_text}",
                    f"link={item.link}",
                    f"summary={_truncate_text(item.summary, 160)}",
                ]
            )
        )

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def _coerce_timeout_seconds(raw_timeout: Any) -> float:
    timeout = _coerce_float(raw_timeout)
    if timeout is None or timeout <= 0:
        return 8.0
    return timeout


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_signed(value: float) -> str:
    return f"{value:+.2f}"


def _format_cny(value: float) -> str:
    return f"¥{value:,.2f}"


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_positive_int(value: Any) -> int | None:
    numeric_value = _coerce_float(value)
    if numeric_value is None:
        return None
    integer_value = int(numeric_value)
    if integer_value <= 0:
        return None
    return integer_value


def _truncate_text(value: str, max_length: int) -> str:
    text = value.strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"