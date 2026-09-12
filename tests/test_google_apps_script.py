import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "google_apps_script_live_proxy.js"


class GoogleAppsScriptQuoteParsingTest(unittest.TestCase):
    def run_javascript(self, expression: str):
        program = f"""
const fs = require("fs");
const vm = require("vm");
const context = {{ console }};
vm.createContext(context);
vm.runInContext(fs.readFileSync({json.dumps(str(SCRIPT_PATH))}, "utf8"), context);
const result = vm.runInContext({json.dumps(expression)}, context);
process.stdout.write(JSON.stringify(result));
"""
        completed = subprocess.run(
            ["node", "-e", program],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_split_yahoo_japan_change_is_parsed(self):
        expression = """parseYahooJapanQuote("9716.T", `<main><div>1,239</div><dt>前日比</dt><dd><span>+6</span><span>(+0.49%)</span></dd><li>リアルタイム株価</li><time>8/21</time></main>`)"""

        quote = self.run_javascript(expression)

        self.assertEqual(quote["price"], 1239)
        self.assertEqual(quote["previous_close"], 1233)
        self.assertEqual(quote["change"], 6)
        self.assertAlmostEqual(quote["change_percent"], 6 / 1233 * 100)

    def test_unchanged_quote_is_valid(self):
        quote = self.run_javascript('quoteResult(1000, 1000, null, "JPY", "", "CLOSED")')

        self.assertEqual(quote["change"], 0)
        self.assertEqual(quote["change_percent"], 0)

    def test_percent_split_into_four_nodes_is_parsed(self):
        expression = """parseYahooJapanQuote("7488.N", `<main><div>5,140</div><dt>前日比</dt><dd><span>+130</span><span>(</span><span>+2.59</span><span>%</span><span>)</span></dd><li>15分ディレイ株価</li><time>09/09</time><time>15:30</time></main>`)"""

        quote = self.run_javascript(expression)

        self.assertEqual(quote["price"], 5140)
        self.assertEqual(quote["previous_close"], 5010)
        self.assertAlmostEqual(quote["change_percent"], 130 / 5010 * 100)
        self.assertTrue(quote["quote_time"])

    def test_market_suffix_detection(self):
        values = self.run_javascript('[isJapanMarketSymbol("7203.T"), isJapanMarketSymbol("7488.N"), isYahooJapanQuoteSymbol("8931224C"), isYahooJapanQuoteSymbol("KXIAY")]')
        self.assertEqual(values, [True, True, True, False])

    def test_japanese_fund_quote_is_parsed(self):
        expression = """parseYahooJapanQuote("8931224C", `<main><div>13,038</div><dt>前日比</dt><dd><span>-43</span><span>(-0.33%)</span></dd><time>08/21</time></main>`)"""

        quote = self.run_javascript(expression)

        self.assertEqual(quote["price"], 13038)
        self.assertEqual(quote["previous_close"], 13081)
        self.assertAlmostEqual(quote["change_percent"], -43 / 13081 * 100)
        self.assertTrue(quote["quote_time"])

    def test_yahoo_japan_history_uses_latest_two_session_closes(self):
        expression = """parseYahooJapanHistoryQuote("7488.N", `<table><tbody>
          <tr><td>2026/9/9</td><td>5,090</td><td>5,090</td><td>5,040</td><td>5,040</td><td>300</td></tr>
          <tr><td>2026/9/8</td><td>5,000</td><td>5,000</td><td>5,000</td><td>5,000</td><td>200</td></tr>
        </tbody></table>`)"""

        quote = self.run_javascript(expression)

        self.assertEqual(quote["price"], 5040)
        self.assertEqual(quote["previous_close"], 5000)
        self.assertAlmostEqual(quote["change_percent"], 0.8)
        self.assertEqual(quote["source"], "yahoo_japan_history")

    def test_regular_market_aligns_previous_close_by_session_date(self):
        expression = """quoteFromDailyChartResult("7203.T", {
          meta: { symbol: "7203.T", currency: "JPY", gmtoffset: 32400, marketState: "REGULAR",
            regularMarketTime: Date.parse("2026-09-10T01:00:00Z") / 1000, regularMarketPrice: 110 },
          timestamp: [Date.parse("2026-09-08T06:30:00Z") / 1000, Date.parse("2026-09-09T06:30:00Z") / 1000],
          indicators: { quote: [{ close: [100, 105] }] }
        })"""

        quote = self.run_javascript(expression)

        self.assertEqual(quote["price"], 110)
        self.assertEqual(quote["previous_close"], 105)
        self.assertEqual(quote["quote_session_date"], "2026-09-10")
        self.assertEqual(quote["previous_close_session_date"], "2026-09-09")

    def test_closed_market_uses_last_completed_session_close(self):
        expression = """quoteFromDailyChartResult("7203.T", {
          meta: { symbol: "7203.T", currency: "JPY", gmtoffset: 32400, marketState: "CLOSED",
            regularMarketTime: Date.parse("2026-09-11T06:30:00Z") / 1000, regularMarketPrice: 108 },
          timestamp: [Date.parse("2026-09-10T06:30:00Z") / 1000, Date.parse("2026-09-11T06:30:00Z") / 1000],
          indicators: { quote: [{ close: [105, 108] }] }
        })"""

        quote = self.run_javascript(expression)

        self.assertEqual(quote["price"], 108)
        self.assertEqual(quote["previous_close"], 105)
        self.assertAlmostEqual(quote["change_percent"], 3 / 105 * 100)

    def test_yahoo_portfolio_tabs_are_parsed(self):
        expression = """parseYahooPortfolioLinks(`<nav>
          <a href="/portfolio/detail?portfolioId=1">S01</a>
          <a href="/portfolio/detail?portfolioId=2&amp;from=nav">新規購入</a>
          <a href="/portfolio/detail?portfolioId=2">新規購入</a>
        </nav>`)"""

        portfolios = self.run_javascript(expression)

        self.assertEqual(portfolios, [
            {"id": 1, "name": "S01"},
            {"id": 2, "name": "新規購入"},
        ])

    def test_yahoo_portfolio_rows_are_parsed(self):
        expression = """parseYahooPortfolioRows(`<table><tbody>
          <tr><td><a href="/quote/9716.T">(株)乃村工藝社</a></td><td>1,250</td></tr>
          <tr><td><a href="https://finance.yahoo.co.jp/quote/7488.N?foo=1">ヤガミ</a></td></tr>
          <tr><td><a href="/quote/9716.T">重複</a></td></tr>
        </tbody></table>`)"""

        symbols = self.run_javascript(expression)

        self.assertEqual(symbols, [
            {"symbol": "9716.T", "name": "(株)乃村工藝社"},
            {"symbol": "7488.N", "name": "ヤガミ"},
        ])


if __name__ == "__main__":
    unittest.main()
