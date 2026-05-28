from __future__ import annotations

import unittest

from homelander_pet.adapters.stock_tracker import (
    DOWN_COLOR,
    UP_COLOR,
    StockHolding,
    StockPosition,
    StockQuote,
    StockTrendTracker,
    parse_stock_positions,
    parse_stock_holdings,
    parse_stock_symbols,
)
from homelander_pet.adapters.news_digest import NewsDigestTracker, NewsItem


class StockTrackerTests(unittest.TestCase):
    def test_parse_stock_symbols_deduplicates_and_normalizes(self) -> None:
        self.assertEqual(
            parse_stock_symbols("AAPL, tsla;msft\nAAPL"),
            ["AAPL", "TSLA", "MSFT"],
        )

    def test_parse_stock_symbols_maps_a_share_codes_to_yahoo_suffixes(self) -> None:
        self.assertEqual(
            parse_stock_symbols("000716,000897,561260"),
            ["000716.SZ", "000897.SZ", "561260.SS"],
        )

    def test_parse_stock_positions_supports_weights_and_deduplicates(self) -> None:
        positions = parse_stock_positions("513010:100,518600:200,513010:50")

        self.assertEqual(
            positions,
            [
                StockPosition(symbol="513010.SS", weight=150.0),
                StockPosition(symbol="518600.SS", weight=200.0),
            ],
        )

    def test_snapshot_aggregates_quotes(self) -> None:
        quote_map = {
            "AAPL": StockQuote(symbol="AAPL", last_price=110.0, previous_close=100.0, change=10.0, change_percent=10.0),
            "TSLA": StockQuote(symbol="TSLA", last_price=190.0, previous_close=200.0, change=-10.0, change_percent=-5.0),
        }
        tracker = StockTrendTracker(
            ["AAPL", "TSLA"],
            fetcher=lambda symbol, _timeout_seconds: quote_map[symbol],
            timeout_seconds=1.0,
            refresh_seconds=10.0,
        )

        snapshot = tracker.snapshot()

        self.assertEqual(snapshot.symbols, ["AAPL", "TSLA"])
        self.assertAlmostEqual(snapshot.net_change, 0.0)
        self.assertAlmostEqual(snapshot.net_change_percent, 0.0)
        self.assertEqual(snapshot.direction, "flat")
        self.assertEqual(snapshot.color, UP_COLOR)

    def test_snapshot_uses_weighted_net_change(self) -> None:
        quote_map = {
            "AAA": StockQuote(symbol="AAA", last_price=12.0, previous_close=10.0, change=2.0, change_percent=20.0),
            "BBB": StockQuote(symbol="BBB", last_price=9.0, previous_close=10.0, change=-1.0, change_percent=-10.0),
        }
        tracker = StockTrendTracker(
            ["AAA", "BBB"],
            fetcher=lambda symbol, _timeout_seconds: quote_map[symbol],
            timeout_seconds=1.0,
            refresh_seconds=10.0,
        )
        tracker.positions = [
            StockPosition(symbol="AAA", weight=1.0),
            StockPosition(symbol="BBB", weight=3.0),
        ]

        snapshot = tracker.snapshot()

        self.assertAlmostEqual(snapshot.net_change, -1.0)
        self.assertEqual(snapshot.direction, "down")
        self.assertEqual(snapshot.color, DOWN_COLOR)

    def test_snapshot_returns_down_color_for_negative_net_change(self) -> None:
        tracker = StockTrendTracker(
            ["AAPL"],
            fetcher=lambda _symbol, _timeout_seconds: StockQuote(
                symbol="AAPL",
                last_price=95.0,
                previous_close=100.0,
                change=-5.0,
                change_percent=-5.0,
            ),
        )

        snapshot = tracker.snapshot()

        self.assertEqual(snapshot.direction, "down")
        self.assertEqual(snapshot.color, DOWN_COLOR)

    def test_current_pnl_uses_average_cost_and_live_quotes(self) -> None:
        quote_map = {
            "AAA": StockQuote(symbol="AAA", last_price=12.0, previous_close=10.0, change=2.0, change_percent=20.0),
            "BBB": StockQuote(symbol="BBB", last_price=9.0, previous_close=10.0, change=-1.0, change_percent=-10.0),
        }
        tracker = StockTrendTracker(
            ["AAA", "BBB"],
            fetcher=lambda symbol, _timeout_seconds: quote_map[symbol],
            timeout_seconds=1.0,
            refresh_seconds=10.0,
        )

        snapshot = tracker.current_pnl(
            [
                StockHolding(symbol="AAA", shares=10.0, average_cost=8.0),
                StockHolding(symbol="BBB", shares=20.0, average_cost=11.0),
            ]
        )

        self.assertAlmostEqual(snapshot.cost_basis, 300.0)
        self.assertAlmostEqual(snapshot.market_value, 300.0)
        self.assertAlmostEqual(snapshot.net_pnl, 0.0)
        self.assertAlmostEqual(snapshot.net_pnl_percent, 0.0)
        self.assertEqual(snapshot.direction, "flat")
        self.assertEqual(snapshot.color, UP_COLOR)
        self.assertAlmostEqual(snapshot.positions[0].pnl, 40.0)
        self.assertAlmostEqual(snapshot.positions[1].pnl, -40.0)

    def test_daily_pnl_snapshot_uses_env_style_share_counts(self) -> None:
        quote_map = {
            "AAA": StockQuote(symbol="AAA", last_price=13.0, previous_close=10.0, change=3.0, change_percent=30.0),
            "BBB": StockQuote(symbol="BBB", last_price=9.0, previous_close=10.0, change=-1.0, change_percent=-10.0),
        }
        tracker = StockTrendTracker(
            ["AAA", "BBB"],
            fetcher=lambda symbol, _timeout_seconds: quote_map[symbol],
            timeout_seconds=1.0,
            refresh_seconds=10.0,
        )
        tracker.positions = [
            StockPosition(symbol="AAA", weight=10.0),
            StockPosition(symbol="BBB", weight=20.0),
        ]

        snapshot = tracker.daily_pnl_snapshot()

        self.assertAlmostEqual(snapshot.market_value, 310.0)
        self.assertAlmostEqual(snapshot.previous_close_value, 300.0)
        self.assertAlmostEqual(snapshot.net_pnl, 10.0)
        self.assertAlmostEqual(snapshot.net_pnl_percent, 10.0 / 300.0 * 100.0)
        self.assertEqual(snapshot.direction, "up")
        self.assertEqual(snapshot.color, UP_COLOR)

    def test_parse_stock_holdings_supports_weights_and_deduplicates(self) -> None:
        holdings = parse_stock_holdings("513010:100:5.00,518600:200:1.50,513010:50:7.00")

        self.assertEqual(
            holdings,
            [
                StockHolding(symbol="513010.SS", shares=150.0, average_cost=5.666666666666667),
                StockHolding(symbol="518600.SS", shares=200.0, average_cost=1.5),
            ],
        )

        def test_daily_news_digest_filters_and_orders_items(self) -> None:
                feed_xml = {
                        "https://example.com/news.xml": """
                                <rss>
                                    <channel>
                                        <title>Example News</title>
                                        <item>
                                            <title>AI chips surge</title>
                                            <link>https://example.com/ai</link>
                                            <pubDate>Tue, 26 May 2026 10:00:00 GMT</pubDate>
                                            <description>AI and semiconductor stocks rally.</description>
                                        </item>
                                        <item>
                                            <title>Sports finals recap</title>
                                            <link>https://example.com/sports</link>
                                            <pubDate>Tue, 26 May 2026 09:00:00 GMT</pubDate>
                                            <description>Finals wrap up the season.</description>
                                        </item>
                                    </channel>
                                </rss>
                        """,
                        "https://example.com/atom.xml": """
                                <feed xmlns="http://www.w3.org/2005/Atom">
                                    <title>Atom Source</title>
                                    <entry>
                                        <title>Markets watch inflation</title>
                                        <link href="https://example.com/markets" />
                                        <updated>2026-05-26T11:00:00Z</updated>
                                        <summary>Inflation data takes center stage.</summary>
                                    </entry>
                                </feed>
                        """,
                }

                tracker = NewsDigestTracker(
                        ["https://example.com/news.xml", "https://example.com/atom.xml"],
                        fetcher=lambda url, _timeout_seconds: feed_xml[url],
                        timeout_seconds=1.0,
                        max_items_per_feed=5,
                        default_limit=10,
                )

                snapshot = tracker.daily_digest(query="AI")

                self.assertEqual(snapshot.source_count, 2)
                self.assertEqual(len(snapshot.items), 1)
                self.assertEqual(snapshot.items[0].title, "AI chips surge")
                self.assertEqual(snapshot.items[0].source, "Example News")
                self.assertEqual(snapshot.items[0].link, "https://example.com/ai")


if __name__ == "__main__":
    unittest.main()