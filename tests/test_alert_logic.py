import time
import unittest

from app import Alert, Quote, evaluate_quote, format_alert, should_send


class AlertLogicTest(unittest.TestCase):
    def test_evaluate_quote_creates_up_alert(self):
        quote = Quote("AAPL", "Apple", 105, 100, 5, "USD", None)
        alert = evaluate_quote(
            quote,
            {"symbol": "AAPL"},
            {"default_up_threshold_percent": 3, "default_down_threshold_percent": -3},
        )

        self.assertIsNotNone(alert)
        self.assertEqual(alert.direction, "up")
        self.assertEqual(alert.threshold_percent, 3)

    def test_evaluate_quote_creates_down_alert(self):
        quote = Quote("7203.T", "トヨタ自動車", 95, 100, -5, "JPY", None)
        alert = evaluate_quote(
            quote,
            {"symbol": "7203.T"},
            {"default_up_threshold_percent": 3, "default_down_threshold_percent": -3},
        )

        self.assertIsNotNone(alert)
        self.assertEqual(alert.direction, "down")
        self.assertEqual(alert.threshold_percent, -3)

    def test_should_send_respects_cooldown(self):
        now = time.time()
        alert = Alert("AAPL", "Apple", "up", 105, 100, 5, 3, "USD", None)
        state = {"sent": {"AAPL:up": now - 60}}

        self.assertFalse(should_send(alert, state, cooldown_hours=24, now=now))
        self.assertTrue(should_send(alert, state, cooldown_hours=0.001, now=now))

    def test_format_alert_contains_core_fields(self):
        alert = Alert("AAPL", "Apple", "up", 105, 100, 5.25, 3, "USD", None)
        message = format_alert(alert)

        self.assertIn("値上がり通知", message)
        self.assertIn("Apple (AAPL)", message)
        self.assertIn("+5.25%", message)


if __name__ == "__main__":
    unittest.main()
