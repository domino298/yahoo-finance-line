import unittest
from datetime import datetime, timezone

from app import (
    is_japan_market_symbol,
    is_yahoo_japan_quote_symbol,
    parse_yahoo_japan_history_html,
    parse_yahoo_japan_quote_html,
    quote_from_daily_chart_result,
)


class YahooJapanQuoteParsingTest(unittest.TestCase):
    def test_parses_split_change_and_percent(self):
        page = """
        <main>
          <h2>(株)乃村工藝社</h2>
          <div>1,239</div>
          <dt>前日比</dt>
          <dd><span>+6</span><span>(+0.49%)</span></dd>
        </main>
        """

        quote = parse_yahoo_japan_quote_html("9716.T", page, "(株)乃村工藝社")

        self.assertEqual(quote.price, 1239)
        self.assertEqual(quote.previous_close, 1233)
        self.assertAlmostEqual(quote.change_percent, 6 / 1233 * 100)
        self.assertIsNone(quote.market_time)

    def test_parses_combined_negative_change(self):
        page = """
        <main>
          <div>1,460</div>
          <dt>前日比</dt>
          <dd>-5 (-0.34%)</dd>
        </main>
        """

        quote = parse_yahoo_japan_quote_html("9622.T", page)

        self.assertEqual(quote.price, 1460)
        self.assertEqual(quote.previous_close, 1465)
        self.assertAlmostEqual(quote.change_percent, -5 / 1465 * 100)

    def test_parses_percent_split_into_four_html_nodes(self):
        page = """
        <main>
          <div>5,140</div>
          <dt>前日比</dt>
          <dd><span>+130</span><span>(</span><span>+2.59</span><span>%</span><span>)</span></dd>
          <li>15分ディレイ株価</li><time>09/09</time><time>15:30</time>
        </main>
        """

        quote = parse_yahoo_japan_quote_html("7488.N", page)

        self.assertEqual(quote.price, 5140)
        self.assertEqual(quote.previous_close, 5010)
        self.assertAlmostEqual(quote.change_percent, 130 / 5010 * 100)
        self.assertIsNotNone(quote.market_time)

    def test_does_not_turn_unavailable_quote_into_zero_percent(self):
        page = """
        <main>
          <dt>前日比</dt><dd>--- (---%)</dd>
          <dt>前日終値</dt><dd>4,130 (06/26)</dd>
        </main>
        """

        with self.assertRaisesRegex(RuntimeError, "current Yahoo Japan price"):
            parse_yahoo_japan_quote_html("4748.T", page)

    def test_recognizes_supported_japan_market_suffixes(self):
        for symbol in ("7203.T", "7488.N", "1234.S", "5678.F"):
            with self.subTest(symbol=symbol):
                self.assertTrue(is_japan_market_symbol(symbol))
        self.assertFalse(is_japan_market_symbol("AAPL"))

    def test_parses_japanese_fund_code_and_quote_date(self):
        page = """
        <main>
          <div>13,038</div>
          <dt>前日比</dt>
          <dd><span>-43</span><span>(-0.33%)</span></dd>
          <time>08/21</time>
        </main>
        """

        quote = parse_yahoo_japan_quote_html("8931224C", page)

        self.assertTrue(is_yahoo_japan_quote_symbol("8931224C"))
        self.assertFalse(is_yahoo_japan_quote_symbol("KXIAY"))
        self.assertEqual(quote.price, 13038)
        self.assertEqual(quote.previous_close, 13081)
        self.assertAlmostEqual(quote.change_percent, -43 / 13081 * 100)
        self.assertIsNotNone(quote.market_time)

    def test_parses_latest_two_trading_session_closes_from_history(self):
        page = """
        <table><thead><tr><th>日付</th><th>始値</th><th>高値</th><th>安値</th><th>終値</th></tr></thead>
        <tbody>
          <tr><td>2026/9/9</td><td>5,090</td><td>5,090</td><td>5,040</td><td>5,040</td><td>300</td></tr>
          <tr><td>2026/9/8</td><td>5,000</td><td>5,000</td><td>5,000</td><td>5,000</td><td>200</td></tr>
        </tbody></table>
        """

        quote = parse_yahoo_japan_history_html("7488.N", page)

        self.assertEqual(quote.price, 5040)
        self.assertEqual(quote.previous_close, 5000)
        self.assertAlmostEqual(quote.change_percent, 0.8)

    @staticmethod
    def timestamp(value: str) -> int:
        return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())

    def chart_result(self, market_state: str, market_time: str, session_dates: list[str], closes: list[float], price=110):
        return {
            "meta": {
                "symbol": "7203.T",
                "currency": "JPY",
                "gmtoffset": 32400,
                "marketState": market_state,
                "regularMarketTime": self.timestamp(market_time),
                "regularMarketPrice": price,
            },
            "timestamp": [self.timestamp(value) for value in session_dates],
            "indicators": {"quote": [{"close": closes}]},
        }

    def test_regular_market_uses_latest_prior_session_when_today_candle_is_absent(self):
        result = self.chart_result(
            "REGULAR",
            "2026-09-10T01:00:00",
            ["2026-09-08T06:30:00", "2026-09-09T06:30:00"],
            [100, 105],
            price=110,
        )

        quote = quote_from_daily_chart_result("7203.T", result)

        self.assertEqual(quote.price, 110)
        self.assertEqual(quote.previous_close, 105)
        self.assertAlmostEqual(quote.change_percent, 5 / 105 * 100)

    def test_regular_market_ignores_current_session_daily_candle_for_previous_close(self):
        result = self.chart_result(
            "REGULAR",
            "2026-09-10T05:00:00",
            ["2026-09-08T06:30:00", "2026-09-09T06:30:00", "2026-09-10T06:30:00"],
            [100, 105, 109],
            price=110,
        )

        quote = quote_from_daily_chart_result("7203.T", result)

        self.assertEqual(quote.price, 110)
        self.assertEqual(quote.previous_close, 105)

    def test_closed_market_uses_latest_completed_close_and_prior_trading_session(self):
        result = self.chart_result(
            "CLOSED",
            "2026-09-11T06:30:00",
            ["2026-09-09T06:30:00", "2026-09-10T06:30:00", "2026-09-11T06:30:00"],
            [100, 105, 108],
            price=108,
        )

        quote = quote_from_daily_chart_result("7203.T", result)

        self.assertEqual(quote.price, 108)
        self.assertEqual(quote.previous_close, 105)
        self.assertAlmostEqual(quote.change_percent, 3 / 105 * 100)

    def test_preopen_after_weekend_uses_friday_close_and_thursday_close(self):
        result = self.chart_result(
            "PRE",
            "2026-09-11T06:30:00",
            ["2026-09-10T06:30:00", "2026-09-11T06:30:00"],
            [105, 108],
            price=108,
        )

        quote = quote_from_daily_chart_result("7203.T", result)

        self.assertEqual(quote.price, 108)
        self.assertEqual(quote.previous_close, 105)


if __name__ == "__main__":
    unittest.main()
