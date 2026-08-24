#!/usr/bin/env python3
import json
import urllib.error
import argparse
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from app import evaluate_quote, fetch_quote, load_config
from portfolio_master import load_master_payload


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_CONFIG_PATH = ROOT / "config.example.json"
PORTFOLIO_RATES_PATH = ROOT / "portfolio_rates.json"
PORTFOLIOS_PATH = ROOT / "portfolios.json"
SYNC_STATUS_PATH = ROOT / "sync_status.json"
SYNC_SCRIPT_PATH = ROOT / "sync_yahoo_portfolios.py"


INDEX_HTML = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Yahoo Finance LINE Alert 確認</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #1f2933;
      --muted: #667085;
      --line: #d9dee7;
      --accent: #0f766e;
      --up: #b42318;
      --down: #175cd3;
      --warn: #b54708;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", sans-serif;
      font-size: 15px;
      letter-spacing: 0;
    }
    header {
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    .wrap {
      width: min(1120px, calc(100vw - 32px));
      margin: 0 auto;
    }
    .topbar {
      min-height: 72px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 {
      margin: 0;
      font-size: 22px;
      line-height: 1.25;
      font-weight: 700;
    }
    .status {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      white-space: nowrap;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--warn);
    }
    main {
      padding: 24px 0 40px;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .metric, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .metric {
      padding: 16px;
      min-height: 86px;
    }
    .label {
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }
    .value {
      font-size: 24px;
      line-height: 1.1;
      font-weight: 700;
    }
    .panel {
      overflow: hidden;
    }
    .tabs {
      display: flex;
      gap: 6px;
      overflow-x: auto;
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }
    .tabs[hidden] {
      display: none;
    }
    .filter-tabs {
      background: #ffffff;
    }
    .tab {
      flex: 0 0 auto;
      min-height: 34px;
      border-radius: 6px;
      padding: 0 10px;
      white-space: nowrap;
    }
    .tab.active {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
      font-weight: 700;
    }
    .panel-head {
      min-height: 56px;
      padding: 12px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--line);
    }
    .panel-title {
      font-size: 16px;
      font-weight: 700;
    }
    .actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    button {
      appearance: none;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      min-height: 36px;
      padding: 0 12px;
      font: inherit;
      cursor: pointer;
    }
    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
      font-weight: 700;
    }
    button:disabled {
      cursor: wait;
      opacity: 0.7;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th, td {
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: middle;
    }
    th {
      background: #fbfcfe;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    tr:last-child td { border-bottom: 0; }
    .symbol {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-weight: 700;
    }
    .muted { color: var(--muted); }
    .up { color: var(--up); font-weight: 700; }
    .down { color: var(--down); font-weight: 700; }
    .alert {
      color: var(--warn);
      font-weight: 700;
    }
    .note {
      margin: 14px 0 0;
      color: var(--muted);
      line-height: 1.65;
    }
    .empty {
      padding: 32px 16px;
      color: var(--muted);
      text-align: center;
    }
    @media (max-width: 780px) {
      .topbar { align-items: flex-start; flex-direction: column; padding: 16px 0; }
      .status { white-space: normal; }
      .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .panel-head { align-items: flex-start; flex-direction: column; }
      table { min-width: 820px; }
      .table-scroll { overflow-x: auto; }
    }
  </style>
</head>
<body>
  <header>
    <div class="wrap topbar">
      <h1>Yahoo Finance LINE Alert 確認</h1>
      <div class="status"><span class="dot" id="statusDot"></span><span id="statusText">読み込み中</span></div>
    </div>
  </header>
  <main class="wrap">
    <section class="summary" aria-label="summary">
      <div class="metric"><div class="label">登録銘柄</div><div class="value" id="symbolCount">-</div></div>
      <div class="metric"><div class="label">同期状態</div><div class="value" id="syncStatus">-</div></div>
    </section>

    <section class="panel">
      <div class="tabs filter-tabs" id="filterTabs" aria-label="filter tabs"></div>
      <div class="tabs" id="portfolioTabs" aria-label="portfolio tabs"></div>
      <div class="panel-head">
        <div>
          <div class="panel-title">銘柄一覧</div>
          <div class="muted" id="sourceText"></div>
        </div>
        <div class="actions">
          <button id="reloadButton">再読み込み</button>
          <button class="primary" id="quoteButton">現在値を確認</button>
        </div>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>銘柄コード</th>
              <th>ポートフォリオ</th>
              <th>名称</th>
              <th>現在値</th>
              <th>前日比</th>
              <th>騰落率</th>
              <th>判定</th>
            </tr>
          </thead>
          <tbody id="rows"></tbody>
        </table>
      </div>
      <div class="empty" id="empty" hidden>該当する銘柄がありません。</div>
    </section>
    <p class="note" id="note"></p>
  </main>
  <script>
    let currentConfig = null;
    let currentPortfolios = [];
    let currentPortfolioId = null;
    let currentFilter = 'portfolio';
    let currentSyncStatus = {};

    const yen = new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 2 });
    const els = {
      statusDot: document.getElementById('statusDot'),
      statusText: document.getElementById('statusText'),
      symbolCount: document.getElementById('symbolCount'),
      syncStatus: document.getElementById('syncStatus'),
      filterTabs: document.getElementById('filterTabs'),
      portfolioTabs: document.getElementById('portfolioTabs'),
      sourceText: document.getElementById('sourceText'),
      rows: document.getElementById('rows'),
      empty: document.getElementById('empty'),
      note: document.getElementById('note'),
      reloadButton: document.getElementById('reloadButton'),
      quoteButton: document.getElementById('quoteButton')
    };

    function setStatus(text, color) {
      els.statusText.textContent = text;
      els.statusDot.style.background = color;
    }

    function syncStatusLabel() {
      const message = currentSyncStatus.message || '';
      if (currentSyncStatus.ok) return '同期済み';
      if (message.includes('Connection refused')) return 'ブラウザ待ち';
      if (message.includes('ログイン')) return 'ログイン待ち';
      if (message) return '同期待ち';
      return '待機中';
    }

    function rateNumber(rate) {
      return Number(String(rate || '').replace('%', '').replace('+', ''));
    }

    function classifyRate(item, rate) {
      if (item.error) return '';
      const value = rateNumber(rate);
      const upLimit = Number(item.up_threshold_percent ?? currentConfig.default_up_threshold_percent);
      const downLimit = Number(item.down_threshold_percent ?? currentConfig.default_down_threshold_percent);
      if (value >= upLimit) return 'up';
      if (value <= downLimit) return 'down';
      return '';
    }

    function judgeText(rateClass) {
      if (rateClass === 'up') return '値上がり通知対象';
      if (rateClass === 'down') return '値下がり通知対象';
      return '通知なし';
    }

    function activePortfolio() {
      return currentPortfolios.find((p) => String(p.id) === String(currentPortfolioId)) || currentPortfolios[0] || null;
    }

    function extractedRows(direction) {
      const rows = [];
      for (const portfolio of currentPortfolios) {
        for (const item of portfolio.symbols || []) {
          const rateClass = classifyRate(item, item.rate);
          if (rateClass === direction) {
            rows.push({ ...item, portfolio_name: portfolio.name, portfolio_id: portfolio.id });
          }
        }
      }
      return rows.sort((a, b) => {
        const aRate = rateNumber(a.rate);
        const bRate = rateNumber(b.rate);
        return direction === 'up' ? bRate - aRate : aRate - bRate;
      });
    }

    function filterCount(filter) {
      if (filter === 'up') return extractedRows('up').length;
      if (filter === 'down') return extractedRows('down').length;
      return currentPortfolios.length;
    }

    function renderFilterTabs() {
      const filters = [
        { id: 'up', label: `5%以上上昇 (${filterCount('up')})` },
        { id: 'down', label: `5%以下下落 (${filterCount('down')})` }
      ];
      els.filterTabs.innerHTML = '';
      for (const filter of filters) {
        const button = document.createElement('button');
        button.className = filter.id === currentFilter ? 'tab active' : 'tab';
        button.textContent = filter.label;
        button.addEventListener('click', () => {
          currentFilter = filter.id;
          if (currentFilter === 'portfolio') {
            currentPortfolioId = currentPortfolios[0]?.id || null;
          }
          renderFilterTabs();
          renderPortfolioTabs();
          renderRows();
        });
        els.filterTabs.appendChild(button);
      }
    }

    function renderPortfolioTabs() {
      els.portfolioTabs.innerHTML = '';
      els.portfolioTabs.hidden = currentPortfolios.length === 0;
      for (const portfolio of currentPortfolios) {
        const button = document.createElement('button');
        button.className = currentFilter === 'portfolio' && String(portfolio.id) === String(currentPortfolioId) ? 'tab active' : 'tab';
        button.textContent = `${portfolio.name} (${portfolio.symbols.length})`;
        button.addEventListener('click', () => {
          currentFilter = 'portfolio';
          currentPortfolioId = portfolio.id;
          renderFilterTabs();
          renderPortfolioTabs();
          renderRows();
        });
        els.portfolioTabs.appendChild(button);
      }
    }

    function renderRows() {
      const portfolio = activePortfolio();
      const symbols = currentFilter === 'up'
        ? extractedRows('up')
        : currentFilter === 'down'
          ? extractedRows('down')
          : portfolio
            ? portfolio.symbols
            : (currentConfig.symbols || []);
      els.symbolCount.textContent = symbols.length;
      els.syncStatus.textContent = syncStatusLabel();
      if (currentFilter === 'up') {
        els.sourceText.textContent = `全ポートフォリオ / 5%以上上昇`;
        els.note.textContent = `全ポートフォリオから騰落率が +5%以上の銘柄を抜き出しています。`;
      } else if (currentFilter === 'down') {
        els.sourceText.textContent = `全ポートフォリオ / 5%以下下落`;
        els.note.textContent = `全ポートフォリオから騰落率が -5%以下の銘柄を抜き出しています。`;
      } else {
        els.sourceText.textContent = portfolio
          ? `${portfolio.name} / ${portfolio.count_text}`
          : 'config.json の内容を表示しています。';
        els.note.textContent = portfolio
          ? `Yahooファイナンスの「${portfolio.name}」を表示しています。表示日付: ${portfolio.as_of || '不明'}`
          : 'この一覧がLINE通知アプリの監視対象です。';
      }
      els.rows.innerHTML = '';
      els.empty.hidden = symbols.length > 0;

      for (const item of symbols) {
        const tr = document.createElement('tr');
        tr.dataset.symbol = item.symbol;
        tr.innerHTML = `
          <td class="symbol"></td>
          <td></td>
          <td></td>
          <td class="muted">未確認</td>
          <td class="muted">未確認</td>
          <td class="muted">未確認</td>
          <td class="muted">-</td>
        `;
        tr.children[0].textContent = item.symbol || '';
        tr.children[1].textContent = item.portfolio_name || (portfolio ? portfolio.name : '-');
        tr.children[2].textContent = item.name || '';
        if (item.price || item.change || item.rate) {
          const rateClass = classifyRate(item, item.rate);
          tr.children[3].textContent = item.price || '未確認';
          tr.children[4].textContent = item.change || '-';
          tr.children[4].className = rateClass;
          tr.children[5].textContent = item.rate || item.error || '-';
          tr.children[5].className = rateClass;
          tr.children[6].textContent = item.error ? '取得失敗（前回値）' : judgeText(rateClass);
          tr.children[6].className = item.error ? 'alert' : rateClass || 'muted';
        } else if (item.error) {
          tr.children[3].textContent = '取得失敗';
          tr.children[5].textContent = item.error;
          tr.children[6].textContent = '確認が必要';
          tr.children[6].className = 'alert';
        }
        els.rows.appendChild(tr);
      }
    }

    function renderConfig(data) {
      const previousPortfolioId = currentPortfolioId;
      currentConfig = data.config;
      currentSyncStatus = data.sync_status || {};
      currentPortfolios = data.portfolios?.portfolios || [];
      currentPortfolioId = currentPortfolios.some((portfolio) => String(portfolio.id) === String(previousPortfolioId))
        ? previousPortfolioId
        : currentPortfolios[0]?.id || null;
      renderFilterTabs();
      renderPortfolioTabs();
      renderRows();
      if (currentSyncStatus.message && !currentSyncStatus.ok) {
        setStatus(syncStatusLabel(), '#b54708');
      } else {
        setStatus(data.using_example ? 'サンプル表示中' : '設定読み込み済み', data.using_example ? '#b54708' : '#0f766e');
      }
    }

    async function loadConfig() {
      setStatus('読み込み中', '#b54708');
      const res = await fetch('/api/config');
      if (!res.ok) throw new Error(await res.text());
      renderConfig(await res.json());
    }

    function renderQuotes(data) {
      for (const item of data.quotes) {
        for (const portfolio of currentPortfolios) {
          for (const symbolItem of portfolio.symbols || []) {
            if (symbolItem.symbol !== item.symbol) continue;
            if (item.error) {
              symbolItem.error = item.error;
              symbolItem.change_percent = null;
              symbolItem.alert_direction = null;
              continue;
            }
            const sign = item.change_percent >= 0 ? '+' : '';
            symbolItem.price = `${yen.format(item.price)} ${item.currency || ''}`.trim();
            symbolItem.change = `${sign}${yen.format(item.price - item.previous_close)}`;
            symbolItem.rate = `${sign}${item.change_percent.toFixed(2)}%`;
            symbolItem.change_percent = item.change_percent;
            symbolItem.alert_direction = item.alert_direction;
            symbolItem.error = '';
          }
        }
        const rows = document.querySelectorAll(`tr[data-symbol="${CSS.escape(item.symbol)}"]`);
        for (const tr of rows) {
          if (item.error) {
            tr.children[3].textContent = '取得失敗';
            tr.children[4].textContent = '-';
            tr.children[5].textContent = item.error;
            tr.children[6].textContent = '確認が必要';
            tr.children[6].className = 'alert';
            continue;
          }
          const sign = item.change_percent >= 0 ? '+' : '';
          const upLimit = Number(currentConfig.default_up_threshold_percent);
          const downLimit = Number(currentConfig.default_down_threshold_percent);
          const isAlertUp = item.change_percent >= upLimit;
          const isAlertDown = item.change_percent <= downLimit;
          const rateClass = isAlertUp ? 'up' : isAlertDown ? 'down' : '';
          tr.children[3].textContent = `${yen.format(item.price)} ${item.currency || ''}`.trim();
          tr.children[4].textContent = `${sign}${yen.format(item.price - item.previous_close)}`;
          tr.children[4].className = rateClass;
          tr.children[5].textContent = `${sign}${item.change_percent.toFixed(2)}%`;
          tr.children[5].className = rateClass;
          if (item.alert_direction === 'up') {
            tr.children[6].textContent = '値上がり通知対象';
            tr.children[6].className = 'up';
          } else if (item.alert_direction === 'down') {
            tr.children[6].textContent = '値下がり通知対象';
            tr.children[6].className = 'down';
          } else {
            tr.children[6].textContent = '通知なし';
            tr.children[6].className = 'muted';
          }
        }
      }
      renderFilterTabs();
      renderPortfolioTabs();
      renderRows();
    }

    async function loadQuotes() {
      if (!currentConfig) return;
      els.quoteButton.disabled = true;
      setStatus('現在値を確認中', '#175cd3');
      try {
        const batchSize = Number(currentConfig.quote_batch_size || 20);
        let offset = 0;
        while (true) {
          const res = await fetch(`/api/quotes?offset=${offset}&limit=${batchSize}`);
          if (!res.ok) throw new Error(await res.text());
          const data = await res.json();
          renderQuotes(data);
          if (data.next_offset === null || data.next_offset === undefined) break;
          offset = data.next_offset;
          setStatus(`現在値を確認中 ${Math.min(offset, data.total)} / ${data.total}`, '#175cd3');
          await new Promise((resolve) => setTimeout(resolve, Number(currentConfig.quote_batch_delay_ms || 1000)));
        }
        setStatus('現在値確認済み', '#0f766e');
      } catch (error) {
        setStatus('現在値の取得に失敗', '#b42318');
        els.note.textContent = error.message || '現在値を取得できませんでした。';
      } finally {
        els.quoteButton.disabled = false;
      }
    }

    els.reloadButton.addEventListener('click', loadConfig);
    els.quoteButton.addEventListener('click', loadQuotes);
    loadConfig().catch((error) => {
      setStatus('読み込み失敗', '#b42318');
      els.note.textContent = error.message;
    });
    setInterval(() => {
      loadConfig().catch(() => {});
    }, 60000);
  </script>
</body>
</html>
"""


def load_config_payload() -> tuple[dict, bool]:
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    using_example = path == EXAMPLE_CONFIG_PATH
    if not using_example:
        return load_config(path), using_example
    with path.open(encoding="utf-8") as file:
        return json.load(file), using_example


def load_portfolio_rates() -> Optional[dict]:
    if not PORTFOLIO_RATES_PATH.exists():
        return None
    with PORTFOLIO_RATES_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def load_portfolios() -> Optional[dict]:
    config, _ = load_config_payload()
    if config.get("symbol_source") == "excel":
        _, portfolios = load_master_payload(config, ROOT)
        return portfolios
    if not PORTFOLIOS_PATH.exists():
        return None
    with PORTFOLIOS_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def load_sync_status() -> dict:
    if not SYNC_STATUS_PATH.exists():
        return {}
    with SYNC_STATUS_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def save_sync_status(status: dict) -> None:
    SYNC_STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_yahoo_sync_once() -> None:
    started_at = datetime.now(timezone.utc).isoformat()
    command = [sys.executable, str(SYNC_SCRIPT_PATH), "--quiet"]
    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=240,
        )
        ok = result.returncode == 0
        message = result.stdout.strip() if ok else result.stderr.strip()
        save_sync_status(
            {
                "ok": ok,
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "message": message,
            }
        )
    except Exception as exc:
        save_sync_status(
            {
                "ok": False,
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "message": str(exc),
            }
        )


def start_auto_sync(interval_minutes: int) -> None:
    if interval_minutes <= 0:
        return

    def worker() -> None:
        time.sleep(5)
        while True:
            run_yahoo_sync_once()
            time.sleep(interval_minutes * 60)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()


def json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/":
                self.serve_index()
            elif path == "/api/config":
                self.serve_config()
            elif path == "/api/quotes":
                self.serve_quotes()
            else:
                json_response(self, {"error": "not found"}, status=404)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, status=500)

    def serve_index(self) -> None:
        body = INDEX_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_config(self) -> None:
        config, using_example = load_config_payload()
        json_response(
            self,
            {
                "config": config,
                "using_example": using_example,
                "portfolio_rates": load_portfolio_rates(),
                "portfolios": load_portfolios(),
                "sync_status": load_sync_status(),
            },
        )

    def serve_quotes(self) -> None:
        config, _ = load_config_payload()
        query = parse_qs(urlparse(self.path).query)
        symbols = config.get("symbols", [])
        offset = max(0, int((query.get("offset") or ["0"])[0]))
        limit_value = (query.get("limit") or [""])[0]
        limit = int(limit_value) if limit_value else len(symbols)
        selected_symbols = symbols[offset : offset + limit]
        quotes = []
        for item in selected_symbols:
            symbol = item.get("symbol")
            if not symbol:
                continue
            try:
                quote = fetch_quote(symbol, item.get("name"))
                alert = evaluate_quote(quote, item, config)
                quotes.append(
                    {
                        "symbol": quote.symbol,
                        "name": quote.name,
                        "price": quote.price,
                        "previous_close": quote.previous_close,
                        "change_percent": quote.change_percent,
                        "currency": quote.currency,
                        "alert_direction": alert.direction if alert else None,
                    }
                )
            except (RuntimeError, urllib.error.URLError) as exc:
                quotes.append({"symbol": symbol, "error": str(exc)})
        next_offset = offset + limit
        json_response(
            self,
            {
                "quotes": quotes,
                "total": len(symbols),
                "offset": offset,
                "next_offset": next_offset if next_offset < len(symbols) else None,
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="確認サイトを起動します。")
    parser.add_argument("--host", default="127.0.0.1", help="待ち受けるIPアドレス")
    parser.add_argument("--port", default=8765, type=int, help="待ち受けるポート番号")
    parser.add_argument("--auto-sync-minutes", default=None, type=int, help="Yahooポートフォリオを自動同期する間隔")
    args = parser.parse_args()

    config, _ = load_config_payload()
    interval = args.auto_sync_minutes
    if interval is None:
        interval = int(config.get("yahoo_auto_sync_minutes", 0))
    start_auto_sync(interval)

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    display_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    print(f"確認サイト: http://{display_host}:{args.port}")
    if args.host == "0.0.0.0":
        print("同じネットワーク内の別PCからは、このPCのIPアドレスでアクセスしてください。")
    server.serve_forever()


if __name__ == "__main__":
    main()
