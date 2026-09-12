import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app import Quote, parse_yahoo_japan_history_html, quote_from_daily_chart_result, run_once
from scripts.build_cloud_site import HTML
from tests import test_google_apps_script as gas_tests


def ts(date):
    return int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())


def chart(state=None):
    return {
        "meta": {"symbol": "7203.T", "currency": "JPY", "gmtoffset": 32400,
                 "regularMarketTime": ts("2026-09-10T01:00:00"),
                 "regularMarketPrice": 110, "marketState": state},
        "timestamp": [ts("2026-09-08T00:00:00"), ts("2026-09-09T00:00:00")],
        "indicators": {"quote": [{"close": [100, 105]}]},
    }


class PriceAuditTest(unittest.TestCase):
    def js(self, expression):
        return gas_tests.GoogleAppsScriptQuoteParsingTest().run_javascript(expression)

    def rejects_js_chart(self, data):
        return self.js(f'''(() => {{ try {{ quoteFromDailyChartResult("7203.T", {json.dumps(data)}); return false; }} catch (_) {{ return true; }} }})()''')

    def test_missing_market_state_does_not_replace_current_price_with_old_close(self):
        data = chart()
        quote = quote_from_daily_chart_result("7203.T", data)
        js_quote = self.js(f'quoteFromDailyChartResult("7203.T", {json.dumps(data)})')
        self.assertEqual((quote.price, quote.previous_close), (110, 105))
        self.assertEqual(js_quote["price"], quote.price)
        self.assertEqual(js_quote["previous_close"], quote.previous_close)

    def test_closed_response_without_same_day_candle_is_rejected(self):
        data = chart("CLOSED")
        with self.assertRaises(RuntimeError):
            quote_from_daily_chart_result("7203.T", data)
        self.assertTrue(self.rejects_js_chart(data))

    def test_conflicting_close_is_rejected_instead_of_silently_overwriting_price(self):
        data = chart("CLOSED")
        data["timestamp"].append(ts("2026-09-10T00:00:00"))
        data["indicators"]["quote"][0]["close"].append(109)
        with self.assertRaises(RuntimeError):
            quote_from_daily_chart_result("7203.T", data)
        self.assertTrue(self.rejects_js_chart(data))

    def test_missing_previous_day_candle_cannot_silently_skip_a_day(self):
        data = chart()
        data["indicators"]["quote"][0]["close"][1] = None
        data["timestamp"].insert(0, ts("2026-09-07T00:00:00"))
        data["indicators"]["quote"][0]["close"].insert(0, 99)
        with self.assertRaises(RuntimeError):
            quote_from_daily_chart_result("7203.T", data)
        self.assertTrue(self.rejects_js_chart(data))

    def test_missing_quote_time_is_rejected(self):
        data = chart()
        del data["meta"]["regularMarketTime"]
        with self.assertRaises(RuntimeError):
            quote_from_daily_chart_result("7203.T", data)
        self.assertTrue(self.rejects_js_chart(data))

    def test_float_encoding_does_not_change_five_percent_boundary(self):
        data = chart()
        data["meta"].update(priceHint=2, regularMarketPrice=104.999999)
        data["indicators"]["quote"][0]["close"] = [99, 100]
        quote = quote_from_daily_chart_result("7203.T", data)
        js_quote = self.js(f'quoteFromDailyChartResult("7203.T", {json.dumps(data)})')
        self.assertEqual(quote.change_percent, 5)
        self.assertEqual(js_quote["change_percent"], 5)

    def test_time_only_weekend_quote_is_not_dated_saturday(self):
        self.assertEqual(self.js('''(() => {const OriginalDate=Date; Date=class extends OriginalDate {constructor(...a){super(...(a.length?a:["2026-09-12T07:00:00Z"]));}};return todayJapanTimeIso(15,30);})()'''), "")

    def test_same_day_date_before_close_is_not_moved_to_last_year(self):
        self.assertEqual(self.js('''(() => {const OriginalDate=Date; Date=class extends OriginalDate {constructor(...a){super(...(a.length?a:["2026-09-10T01:00:00Z"]));}};return japanDateTimeIso(9,10,15,30);})()'''), "")

    def test_nonfinite_and_nonpositive_quotes_are_rejected(self):
        for value in (0, -1, float("nan"), float("inf"), None, True):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                Quote("X", "X", value, 100, 0, "JPY", None)

    def test_history_keeps_columns_and_excludes_unfinished_today(self):
        html = '''<table><tr><td>2026/9/10</td><td>111</td><td>112</td><td>109</td><td>110</td></tr>
          <tr><td>2026/9/9</td><td>---</td><td>---</td><td>---</td><td>105</td><td>9999</td></tr>
          <tr><td>2026/9/8</td><td>100</td><td>100</td><td>100</td><td>100</td></tr></table>'''
        now = datetime(2026, 9, 10, 1, tzinfo=timezone.utc)
        quote = parse_yahoo_japan_history_html("7203.T", html, now=now)
        js_quote = self.js(f'parseYahooJapanHistoryQuote("7203.T", {json.dumps(html)}, new Date("2026-09-10T01:00:00Z"))')
        self.assertEqual((quote.price, quote.previous_close), (105, 100))
        self.assertEqual((js_quote["price"], js_quote["previous_close"]), (105, 100))
        self.assertTrue(quote.warning)

    def test_missing_history_close_is_not_replaced_by_volume(self):
        html = '''<table><tr><td>2026/9/9</td><td>100</td><td>100</td><td>100</td><td>---</td><td>9999</td></tr>
          <tr><td>2026/9/8</td><td>100</td><td>100</td><td>100</td><td>100</td></tr></table>'''
        with self.assertRaises((ValueError, RuntimeError)):
            parse_yahoo_japan_history_html("7203.T", html)

    def test_batch_transport_failure_does_not_abort_history_fallback(self):
        result = self.js('''(() => {
          UrlFetchApp = { fetchAll: () => { throw new Error("offline"); } };
          fetchQuoteFromYahooJapanHistory = () => quoteResult(105, 100, null, "JPY", "2026-09-09T06:30:00Z", "CLOSED");
          return fetchQuotes(["7203.T"]);
        })()''')
        self.assertEqual(result["7203.T"]["price"], 105)

    def test_dry_run_does_not_change_notification_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            original = '{"sent": {}}'
            state_path.write_text(original)
            config = {"symbols": [{"symbol": "7203.T"}], "state_file": str(state_path),
                      "default_up_threshold_percent": 5, "default_down_threshold_percent": -5,
                      "quote_delay_seconds": 0}
            with patch("app.load_config", return_value=config), patch("app.fetch_quote", return_value=Quote("7203.T", "X", 110, 100, 10, "JPY", None)), patch("app.send_line_message") as send, contextlib.redirect_stdout(io.StringIO()):
                run_once(Path(directory) / "config.json", dry_run=True)
            self.assertEqual(state_path.read_text(), original)
            send.assert_not_called()


class BrowserLogicAuditTest(unittest.TestCase):
    def run_browser(self, scenario):
        script = HTML.split("<script>", 1)[1].split("</script>", 1)[0]
        script = script.replace("    loadInitialData();", "    globalThis.ready = loadInitialData();")
        program = '''const vm = require("vm");
const node = () => ({ disabled:false, hidden:false, style:{}, textContent:"", innerHTML:"", children:[],
  appendChild(c) {this.children.push(c);}, addEventListener(){}, remove(){} });
const elements = new Map();
const initial = {generated_at:"2026-09-08T01:00:00Z",quote_time:"2026-09-08T01:00:00Z",default_up_threshold_percent:5,default_down_threshold_percent:-5,
portfolios:[{id:1,name:"S01",symbols:[{symbol:"7203.T",price:100,previous_close:100,change:"+0",rate:"0%"}]}]};
const context = {console, Intl, URLSearchParams, window:{setTimeout,clearTimeout},
document:{querySelector(s){if(!elements.has(s))elements.set(s,node());return elements.get(s);},createElement:node,head:node()},
fetch:async()=>({ok:true,json:async()=>JSON.parse(JSON.stringify(initial))})};
vm.createContext(context);
vm.runInContext(SOURCE,context);
vm.runInContext(`globalThis.calls=[]; fetchJsonp=async (url,params)=>{
calls.push(params); if(params.action) throw new Error("expired cookie");
return {quotes:{"7203.T":{price:106,previous_close:100,change_percent:6,quote_time:"2026-09-09T06:30:00Z"}}};};`,context);
(async()=>{await context.ready; let result=await vm.runInContext(SCENARIO,context);process.stdout.write(JSON.stringify(result));})().catch(e=>{console.error(e);process.exitCode=1;});
'''.replace("SOURCE", json.dumps(script)).replace("SCENARIO", json.dumps(scenario))
        completed = subprocess.run(["node", "-e", program], capture_output=True, text=True, check=True)
        return json.loads(completed.stdout)

    def test_open_refreshes_existing_symbols_even_if_portfolio_sync_fails(self):
        result = self.run_browser('({price:payload.portfolios[0].symbols[0].price,calls,disabled:els.refreshButton.disabled})')
        self.assertEqual(result["price"], 106)
        self.assertEqual(sum("symbols" in call for call in result["calls"]), 1)
        self.assertFalse(result["disabled"])

    def test_null_price_is_rejected_and_rate_is_recalculated(self):
        result = self.run_browser('''(() => {let rejected=false;try{normalizeQuote({price:null,previous_close:100});}catch(_){rejected=true;}
return {rejected,percent:normalizeQuote({price:105,previous_close:100,change_percent:4.99}).change_percent};})()''')
        self.assertTrue(result["rejected"])
        self.assertEqual(result["percent"], 5)

    def test_repeated_click_does_not_start_parallel_refreshes(self):
        result = self.run_browser('''(async()=>{calls=[];await Promise.all([refreshData(),refreshData()]);return {calls,disabled:els.refreshButton.disabled};})()''')
        self.assertEqual(sum("symbols" in call for call in result["calls"]), 1)
        self.assertFalse(result["disabled"])

    def test_all_failures_preserve_price_and_report_failure(self):
        result = self.run_browser('''(async()=>{fetchJsonp=async()=>null;await refreshData();return {price:payload.portfolios[0].symbols[0].price,error:payload.portfolios[0].symbols[0].error,status:els.statusText.textContent,disabled:els.refreshButton.disabled};})()''')
        self.assertEqual(result["price"], 106)
        self.assertTrue(result["error"])
        self.assertIn("取得失敗", result["status"])
        self.assertFalse(result["disabled"])

    def test_transport_outage_stops_after_three_batches(self):
        result = self.run_browser('''(async()=>{
window.setTimeout=(fn)=>{fn();return 0;};
payload.portfolios[0].symbols=Array.from({length:80},(_,i)=>({symbol:`${1000+i}.T`,price:100}));
let attempts=0;fetchJsonp=async()=>{attempts++;throw new Error("offline");};
const result=await refreshLiveQuotes();return {attempts,failed:result.failed,total:result.total};})()''')
        self.assertEqual(result, {"attempts": 3, "failed": 80, "total": 80})
