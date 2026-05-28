from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Sequence


DEFAULT_TRACKER_REFRESH_SECONDS = 60.0
DEFAULT_TRACKER_TIMEOUT_SECONDS = 8.0
UP_COLOR = "#e74c3c"
DOWN_COLOR = "#700be5"


@dataclass(slots=True)
class StockQuote:
    symbol: str
    last_price: float
    previous_close: float
    change: float
    change_percent: float


@dataclass(slots=True)
class StockPosition:
    symbol: str
    weight: float


@dataclass(slots=True)
class StockHolding:
    symbol: str
    shares: float
    average_cost: float


@dataclass(slots=True)
class StockPnLPosition:
    symbol: str
    shares: float
    average_cost: float
    last_price: float
    market_value: float
    cost_basis: float
    pnl: float
    pnl_percent: float
    change: float
    change_percent: float


@dataclass(slots=True)
class StockPnLSnapshot:
    positions: list[StockPnLPosition]
    market_value: float
    cost_basis: float
    net_pnl: float
    net_pnl_percent: float
    direction: str
    color: str
    fetched_at: datetime


@dataclass(slots=True)
class StockDailyPnLSnapshot:
    symbols: list[str]
    quotes: list[StockQuote]
    market_value: float
    previous_close_value: float
    net_pnl: float
    net_pnl_percent: float
    direction: str
    color: str
    fetched_at: datetime


@dataclass(slots=True)
class StockTrendSnapshot:
    symbols: list[str]
    quotes: list[StockQuote]
    net_change: float
    net_change_percent: float
    direction: str
    color: str
    fetched_at: datetime


def parse_stock_symbols(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []

    symbols: list[str] = []
    for token in re.split(r"[\s,;]+", raw_value.strip()):
        symbol = _normalize_symbol(token)
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def parse_stock_positions(raw_value: str | None) -> list[StockPosition]:
    if not raw_value:
        return []

    positions_by_symbol: dict[str, float] = {}
    ordered_symbols: list[str] = []
    for token in re.split(r"[\s,;]+", raw_value.strip()):
        if not token:
            continue
        raw_symbol, raw_weight = _split_stock_position_token(token)
        symbol = _normalize_symbol(raw_symbol)
        if not symbol:
            continue
        weight = _coerce_float(raw_weight) if raw_weight is not None else 1.0
        if weight is None or weight <= 0:
            continue
        if symbol not in positions_by_symbol:
            ordered_symbols.append(symbol)
            positions_by_symbol[symbol] = 0.0
        positions_by_symbol[symbol] += weight

    return [StockPosition(symbol=symbol, weight=positions_by_symbol[symbol]) for symbol in ordered_symbols]


def load_stock_symbols_from_environment() -> list[str]:
    return [position.symbol for position in load_stock_positions_from_environment()]


def load_stock_positions_from_environment() -> list[StockPosition]:
    for key in ("HOMELANDER_PET_STOCK_CODES", "HOMELANDER_PET_STOCKS"):
        positions = parse_stock_positions(os.environ.get(key))
        if positions:
            return positions
    return []


def load_stock_holdings_from_environment() -> list[StockHolding]:
    for key in ("HOMELANDER_PET_STOCK_HOLDINGS", "HOMELANDER_PET_STOCK_PNL_POSITIONS"):
        holdings = parse_stock_holdings(os.environ.get(key))
        if holdings:
            return holdings
    return []


def parse_stock_holdings(raw_value: str | None) -> list[StockHolding]:
    if not raw_value:
        return []

    holdings_by_symbol: dict[str, StockHolding] = {}
    ordered_symbols: list[str] = []
    for token in re.split(r"[\s,;]+", raw_value.strip()):
        if not token:
            continue
        raw_symbol, raw_shares, raw_average_cost = _split_stock_holding_token(token)
        symbol = _normalize_symbol(raw_symbol)
        shares = _coerce_float(raw_shares)
        average_cost = _coerce_float(raw_average_cost)
        if not symbol or shares is None or average_cost is None or shares <= 0 or average_cost < 0:
            continue
        existing = holdings_by_symbol.get(symbol)
        if existing is None:
            normalized = StockHolding(symbol=symbol, shares=shares, average_cost=average_cost)
            holdings_by_symbol[symbol] = normalized
            ordered_symbols.append(symbol)
            continue
        total_shares = existing.shares + shares
        total_cost = existing.shares * existing.average_cost + shares * average_cost
        holdings_by_symbol[symbol] = StockHolding(
            symbol=symbol,
            shares=total_shares,
            average_cost=(total_cost / total_shares) if total_shares else 0.0,
        )

    return [holdings_by_symbol[symbol] for symbol in ordered_symbols]


class StockTrendTracker:
    def __init__(
        self,
        symbols: Sequence[str],
        *,
        timeout_seconds: float = DEFAULT_TRACKER_TIMEOUT_SECONDS,
        refresh_seconds: float = DEFAULT_TRACKER_REFRESH_SECONDS,
        fetcher: Callable[[str, float], StockQuote] | None = None,
    ) -> None:
        self.positions = [StockPosition(symbol=symbol.strip().upper(), weight=1.0) for symbol in symbols if symbol.strip()]
        self.timeout_seconds = timeout_seconds
        self.refresh_seconds = refresh_seconds
        self._fetcher = fetcher or self._fetch_sina_quote

    @classmethod
    def from_environment(cls) -> "StockTrendTracker | None":
        positions = load_stock_positions_from_environment()
        if not positions:
            return None

        timeout_seconds = _read_float_env("HOMELANDER_PET_STOCK_TIMEOUT_SECONDS", DEFAULT_TRACKER_TIMEOUT_SECONDS)
        refresh_seconds = _read_float_env("HOMELANDER_PET_STOCK_REFRESH_SECONDS", DEFAULT_TRACKER_REFRESH_SECONDS)
        tracker = cls([position.symbol for position in positions], timeout_seconds=timeout_seconds, refresh_seconds=refresh_seconds)
        tracker.positions = positions
        return tracker

    def snapshot(self) -> StockTrendSnapshot:
        quotes: list[StockQuote] = []
        quote_map: dict[str, StockQuote] = {}
        for position in self.positions:
            try:
                quote = self._fetcher(position.symbol, self.timeout_seconds)
            except Exception:  # noqa: BLE001
                continue
            quotes.append(quote)
            quote_map[position.symbol] = quote

        if not quotes:
            raise RuntimeError("no stock quotes could be fetched")

        net_change = sum(quote_map[position.symbol].change * position.weight for position in self.positions if position.symbol in quote_map)
        net_previous_close = sum(quote_map[position.symbol].previous_close * position.weight for position in self.positions if position.symbol in quote_map)
        net_change_percent = (net_change / net_previous_close * 100.0) if net_previous_close else 0.0

        if net_change > 0:
            direction = "up"
            color = UP_COLOR
        elif net_change < 0:
            direction = "down"
            color = DOWN_COLOR
        else:
            direction = "flat"
            color = UP_COLOR

        return StockTrendSnapshot(
            symbols=[quote.symbol for quote in quotes],
            quotes=quotes,
            net_change=net_change,
            net_change_percent=net_change_percent,
            direction=direction,
            color=color,
            fetched_at=datetime.now(tz=UTC),
        )

    def current_pnl(self, holdings: Sequence[StockHolding]) -> StockPnLSnapshot:
        aggregated_holdings: list[StockHolding] = []
        holding_map: dict[str, StockHolding] = {}
        for holding in holdings:
            symbol = holding.symbol.strip().upper()
            if not symbol or holding.shares <= 0:
                continue
            average_cost = holding.average_cost
            if average_cost < 0:
                continue
            existing = holding_map.get(symbol)
            if existing is None:
                normalized = StockHolding(symbol=symbol, shares=holding.shares, average_cost=average_cost)
                holding_map[symbol] = normalized
                aggregated_holdings.append(normalized)
                continue
            total_shares = existing.shares + holding.shares
            total_cost = existing.shares * existing.average_cost + holding.shares * average_cost
            updated = StockHolding(symbol=symbol, shares=total_shares, average_cost=(total_cost / total_shares) if total_shares else 0.0)
            holding_map[symbol] = updated
            aggregated_holdings[aggregated_holdings.index(existing)] = updated

        if not aggregated_holdings:
            raise RuntimeError("no holdings were provided")

        quotes: list[StockQuote] = []
        quote_map: dict[str, StockQuote] = {}
        for holding in aggregated_holdings:
            try:
                quote = self._fetcher(holding.symbol, self.timeout_seconds)
            except Exception:  # noqa: BLE001
                continue
            quotes.append(quote)
            quote_map[holding.symbol] = quote

        if not quotes:
            raise RuntimeError("no stock quotes could be fetched")

        positions: list[StockPnLPosition] = []
        market_value = 0.0
        cost_basis = 0.0
        for holding in aggregated_holdings:
            quote = quote_map.get(holding.symbol)
            if quote is None:
                continue
            holding_cost_basis = holding.shares * holding.average_cost
            holding_market_value = holding.shares * quote.last_price
            holding_pnl = holding_market_value - holding_cost_basis
            holding_pnl_percent = (holding_pnl / holding_cost_basis * 100.0) if holding_cost_basis else 0.0
            positions.append(
                StockPnLPosition(
                    symbol=holding.symbol,
                    shares=holding.shares,
                    average_cost=holding.average_cost,
                    last_price=quote.last_price,
                    market_value=holding_market_value,
                    cost_basis=holding_cost_basis,
                    pnl=holding_pnl,
                    pnl_percent=holding_pnl_percent,
                    change=quote.change,
                    change_percent=quote.change_percent,
                )
            )
            market_value += holding_market_value
            cost_basis += holding_cost_basis

        if not positions:
            raise RuntimeError("no holdings could be priced")

        net_pnl = market_value - cost_basis
        net_pnl_percent = (net_pnl / cost_basis * 100.0) if cost_basis else 0.0
        if net_pnl > 0:
            direction = "up"
            color = UP_COLOR
        elif net_pnl < 0:
            direction = "down"
            color = DOWN_COLOR
        else:
            direction = "flat"
            color = UP_COLOR

        return StockPnLSnapshot(
            positions=positions,
            market_value=market_value,
            cost_basis=cost_basis,
            net_pnl=net_pnl,
            net_pnl_percent=net_pnl_percent,
            direction=direction,
            color=color,
            fetched_at=datetime.now(tz=UTC),
        )

    def current_pnl_from_environment(self) -> StockPnLSnapshot:
        holdings = load_stock_holdings_from_environment()
        if not holdings:
            raise RuntimeError(
                "no stock holdings were configured; set HOMELANDER_PET_STOCK_HOLDINGS="
                "symbol:shares:average_cost entries such as 513010:5800:5.00"
            )
        return self.current_pnl(holdings)

    def daily_pnl_snapshot(self) -> StockDailyPnLSnapshot:
        quotes: list[StockQuote] = []
        quote_map: dict[str, StockQuote] = {}
        for position in self.positions:
            try:
                quote = self._fetcher(position.symbol, self.timeout_seconds)
            except Exception:  # noqa: BLE001
                continue
            quotes.append(quote)
            quote_map[position.symbol] = quote

        if not quotes:
            raise RuntimeError("no stock quotes could be fetched")

        market_value = sum(quote_map[position.symbol].last_price * position.weight for position in self.positions if position.symbol in quote_map)
        previous_close_value = sum(quote_map[position.symbol].previous_close * position.weight for position in self.positions if position.symbol in quote_map)
        net_pnl = market_value - previous_close_value
        net_pnl_percent = (net_pnl / previous_close_value * 100.0) if previous_close_value else 0.0

        if net_pnl > 0:
            direction = "up"
            color = UP_COLOR
        elif net_pnl < 0:
            direction = "down"
            color = DOWN_COLOR
        else:
            direction = "flat"
            color = UP_COLOR

        return StockDailyPnLSnapshot(
            symbols=[quote.symbol for quote in quotes],
            quotes=quotes,
            market_value=market_value,
            previous_close_value=previous_close_value,
            net_pnl=net_pnl,
            net_pnl_percent=net_pnl_percent,
            direction=direction,
            color=color,
            fetched_at=datetime.now(tz=UTC),
        )

    def _fetch_sina_quote(self, symbol: str, timeout_seconds: float) -> StockQuote:
        sina_symbol = _to_sina_symbol(symbol)
        url = f"https://hq.sinajs.cn/list={urllib.parse.quote(sina_symbol, safe='')}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "application/javascript,text/plain,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://finance.sina.com.cn/",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )

        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_text = response.read().decode("gbk", errors="replace")

        match = re.search(r'var\s+hq_str_[^=]+="(?P<data>.*?)";', raw_text)
        if match is None:
            raise RuntimeError(f"missing quote data for {symbol}")

        fields = match.group("data").split(",")
        if len(fields) < 4:
            raise RuntimeError(f"incomplete quote data for {symbol}")

        current_price = _coerce_float(fields[3])
        previous_close = _coerce_float(fields[2])
        if current_price is None or previous_close is None:
            raise RuntimeError(f"incomplete quote data for {symbol}")

        change = current_price - previous_close
        change_percent = (change / previous_close * 100.0) if previous_close else 0.0
        return StockQuote(
            symbol=symbol,
            last_price=current_price,
            previous_close=previous_close,
            change=change,
            change_percent=change_percent,
        )


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _latest_numeric_value(values: Sequence[object]) -> float | None:
    for value in reversed(values):
        converted = _coerce_float(value)
        if converted is not None:
            return converted
    return None


def _split_stock_position_token(token: str) -> tuple[str, str | None]:
    if ":" not in token:
        return token, None
    symbol_part, weight_part = token.rsplit(":", 1)
    return symbol_part, weight_part


def _split_stock_holding_token(token: str) -> tuple[str, str | None, str | None]:
    parts = token.split(":")
    if len(parts) < 3:
        return token, None, None
    symbol_part = ":".join(parts[:-2])
    shares_part = parts[-2]
    average_cost_part = parts[-1]
    return symbol_part, shares_part, average_cost_part


def _to_sina_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if symbol.endswith(".SS"):
        return f"sh{symbol[:-3]}"
    if symbol.endswith(".SZ"):
        return f"sz{symbol[:-3]}"
    if re.fullmatch(r"\d{6}", symbol):
        return f"sh{symbol}" if symbol[0] in {"5", "6", "9"} else f"sz{symbol}"
    return symbol.lower()


def _read_float_env(name: str, default_value: float) -> float:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default_value
    try:
        return float(raw_value)
    except ValueError:
        return default_value


def _normalize_symbol(token: str) -> str | None:
    symbol = token.strip().upper()
    if not symbol:
        return None

    if re.fullmatch(r"\d{6}", symbol):
        market_suffix = ".SS" if symbol[0] in {"5", "6", "9"} else ".SZ"
        return f"{symbol}{market_suffix}"

    return symbol