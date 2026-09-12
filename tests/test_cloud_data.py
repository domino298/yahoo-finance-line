import unittest
from unittest.mock import patch

from app import Quote
from scripts.build_cloud_data import fetch_quote_payloads, quote_payload


class CloudDataFetchTest(unittest.TestCase):
    def test_failed_quotes_are_retried(self):
        symbols = [{"symbol": "A.T"}, {"symbol": "B.T"}]
        config = {
            "quote_delay_seconds": 0,
            "quote_retry_attempts": 2,
            "quote_retry_pause_seconds": 0,
            "quote_retry_delay_seconds": 0,
        }
        responses = [
            {"symbol": "A.T", "error": "temporary"},
            {"symbol": "B.T", "price": 200, "error": ""},
            {"symbol": "A.T", "price": 100, "error": ""},
        ]

        with patch("scripts.build_cloud_data.quote_payload", side_effect=responses) as mocked_fetch:
            result = fetch_quote_payloads(symbols, config)

        self.assertEqual(mocked_fetch.call_count, 3)
        self.assertEqual(result["A.T"]["price"], 100)
        self.assertEqual(result["B.T"]["price"], 200)

    def test_symbols_without_chart_fallback_are_fetched_first(self):
        symbols = [
            {"symbol": "7203.T"},
            {"symbol": "KXIAY"},
            {"symbol": "7488.N"},
            {"symbol": "8931224C"},
        ]
        config = {
            "quote_delay_seconds": 0,
            "quote_retry_attempts": 0,
        }
        fetched = []

        def fake_quote_payload(item, _config):
            fetched.append(item["symbol"])
            return {"symbol": item["symbol"], "price": 1, "error": ""}

        with patch("scripts.build_cloud_data.quote_payload", side_effect=fake_quote_payload):
            fetch_quote_payloads(symbols, config)

        self.assertEqual(fetched[:2], ["7488.N", "8931224C"])

    def test_tokyo_stock_uses_hardened_shared_quote_route(self):
        config = {"default_up_threshold_percent": 5, "default_down_threshold_percent": -5}
        quote = Quote("7203.T", "トヨタ", 101, 100, 1, "JPY", 1)

        with patch("scripts.build_cloud_data.fetch_quote", return_value=quote) as shared_fetch:
            result = quote_payload({"symbol": "7203.T", "name": "トヨタ"}, config)

        shared_fetch.assert_called_once()
        self.assertEqual(result["change_percent"], 1)

    def test_japanese_fund_uses_yahoo_japan_route(self):
        config = {"default_up_threshold_percent": 5, "default_down_threshold_percent": -5}
        quote = Quote("8931224C", "投資信託", 99, 100, -1, "JPY", 1)

        with patch("scripts.build_cloud_data.fetch_quote", return_value=quote) as japan_fetch:
            result = quote_payload({"symbol": "8931224C", "name": "投資信託"}, config)

        japan_fetch.assert_called_once()
        self.assertEqual(result["change_percent"], -1)


if __name__ == "__main__":
    unittest.main()
