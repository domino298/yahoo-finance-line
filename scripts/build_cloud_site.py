#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
INDEX_PATH = DOCS_DIR / "index.html"


HTML = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>株価確認サイト</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
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
    header { border-bottom: 1px solid var(--line); background: var(--panel); }
    .wrap { width: min(1120px, calc(100vw - 32px)); margin: 0 auto; }
    .topbar { min-height: 72px; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    .top-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
    h1 { margin: 0; font-size: 22px; line-height: 1.25; }
    main { padding: 24px 0 40px; }
    .gate, .metric, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .gate { max-width: 480px; margin: 36px auto; padding: 20px; }
    .gate label { display: block; color: var(--muted); margin-bottom: 8px; }
    .gate-row { display: flex; gap: 8px; }
    input {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 12px;
      font: inherit;
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
      white-space: nowrap;
    }
    button.active, button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
      font-weight: 700;
    }
    .summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
    .metric { padding: 16px; min-height: 86px; }
    .label { color: var(--muted); font-size: 13px; margin-bottom: 8px; }
    .value { font-size: 24px; line-height: 1.1; font-weight: 700; }
    .tabs { display: flex; gap: 6px; overflow-x: auto; padding: 12px 16px; border-bottom: 1px solid var(--line); background: #fbfcfe; }
    .filter-tabs { background: #fff; }
    .panel { overflow: hidden; }
    .panel-head { min-height: 56px; padding: 12px 16px; border-bottom: 1px solid var(--line); }
    .panel-title { font-weight: 700; }
    .muted { color: var(--muted); }
    .error { color: var(--warn); font-weight: 700; }
    .table-scroll { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 12px 14px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }
    th { background: #fbfcfe; color: var(--muted); font-size: 12px; font-weight: 700; }
    .symbol { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-weight: 700; }
    .up { color: var(--up); font-weight: 700; }
    .down { color: var(--down); font-weight: 700; }
    .empty { padding: 32px 16px; color: var(--muted); text-align: center; display: none; }
    [hidden] { display: none !important; }
    @media (max-width: 780px) {
      .wrap { width: min(100vw - 16px, 1120px); }
      .topbar { align-items: flex-start; flex-direction: column; padding: 16px 0; gap: 10px; }
      .top-actions { width: 100%; justify-content: space-between; }
      h1 { font-size: 20px; }
      .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .gate-row { flex-direction: column; }
      .table-scroll { overflow-x: visible; }
      table { min-width: 0; table-layout: fixed; }
      th, td { padding: 10px 6px; font-size: 12px; line-height: 1.35; }
      th:nth-child(1), td:nth-child(1),
      th:nth-child(2), td:nth-child(2),
      th:nth-child(7), td:nth-child(7) { display: none; }
      th:nth-child(3), td:nth-child(3) { width: 42%; }
      th:nth-child(4), td:nth-child(4) { width: 20%; }
      th:nth-child(5), td:nth-child(5) { width: 18%; }
      th:nth-child(6), td:nth-child(6) { width: 20%; }
      td:nth-child(3) {
        word-break: keep-all;
        overflow-wrap: anywhere;
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="wrap topbar">
      <h1>株価確認サイト</h1>
      <div class="top-actions">
        <button id="refreshButton" type="button" disabled>更新</button>
        <div class="muted" id="statusText">パスワード未入力</div>
      </div>
    </div>
  </header>
  <main class="wrap">
    <section class="gate" id="gate">
      <label for="password">パスワード</label>
      <div class="gate-row">
        <input id="password" type="password" autocomplete="current-password">
        <button class="primary" id="unlockButton">開く</button>
      </div>
      <p class="error" id="gateError" hidden>パスワードが違うか、データを開けませんでした。</p>
    </section>
    <section id="app" hidden>
      <section class="summary">
        <div class="metric"><div class="label">5%以上上昇</div><div class="value" id="upCount">-</div></div>
        <div class="metric"><div class="label">5%以下下落</div><div class="value" id="downCount">-</div></div>
      </section>
      <section class="panel">
        <div class="tabs filter-tabs" id="filterTabs"></div>
        <div class="tabs" id="portfolioTabs"></div>
        <div class="panel-head">
          <div class="panel-title">銘柄一覧</div>
          <div class="muted" id="sourceText"></div>
        </div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>銘柄コード</th><th>ポートフォリオ</th><th>名称</th><th>現在値</th><th>前日比</th><th>騰落率</th><th>判定</th>
              </tr>
            </thead>
            <tbody id="rows"></tbody>
          </table>
        </div>
        <div class="empty" id="empty">該当する銘柄がありません。</div>
      </section>
    </section>
  </main>
  <script>
    let payload = null;
    let rows = [];
    let currentFilter = "portfolio";
    let currentPortfolioId = null;
    const els = {
      gate: document.querySelector("#gate"),
      app: document.querySelector("#app"),
      password: document.querySelector("#password"),
      unlockButton: document.querySelector("#unlockButton"),
      gateError: document.querySelector("#gateError"),
      refreshButton: document.querySelector("#refreshButton"),
      statusText: document.querySelector("#statusText"),
      upCount: document.querySelector("#upCount"),
      downCount: document.querySelector("#downCount"),
      filterTabs: document.querySelector("#filterTabs"),
      portfolioTabs: document.querySelector("#portfolioTabs"),
      sourceText: document.querySelector("#sourceText"),
      rows: document.querySelector("#rows"),
      empty: document.querySelector("#empty")
    };
    const yen = new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 2 });
    function bytesFromBase64(text) {
      return Uint8Array.from(atob(text), (char) => char.charCodeAt(0));
    }
    async function decryptData(password) {
      const encrypted = await fetch(`encrypted-data.json?v=${Date.now()}`, { cache: "no-store" }).then((res) => res.json());
      const encoder = new TextEncoder();
      const baseKey = await crypto.subtle.importKey("raw", encoder.encode(password), "PBKDF2", false, ["deriveKey"]);
      const key = await crypto.subtle.deriveKey(
        { name: "PBKDF2", hash: "SHA-256", salt: bytesFromBase64(encrypted.salt), iterations: encrypted.iterations },
        baseKey,
        { name: "AES-GCM", length: 256 },
        false,
        ["decrypt"]
      );
      const plain = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: bytesFromBase64(encrypted.iv) },
        key,
        bytesFromBase64(encrypted.ciphertext)
      );
      return JSON.parse(new TextDecoder().decode(plain));
    }
    function rateNumber(item) {
      if (typeof item.change_percent === "number") return item.change_percent;
      return Number(String(item.rate || "").replace("%", "").replace("+", "")) || 0;
    }
    function rateClass(item) {
      if (item.alert_direction === "up" || rateNumber(item) >= Number(payload.default_up_threshold_percent)) return "up";
      if (item.alert_direction === "down" || rateNumber(item) <= Number(payload.default_down_threshold_percent)) return "down";
      return "";
    }
    function judgeText(item) {
      const kind = rateClass(item);
      if (kind === "up") return "値上がり通知対象";
      if (kind === "down") return "値下がり通知対象";
      if (item.error) return "取得失敗";
      return "通知なし";
    }
    function buildRows() {
      rows = [];
      for (const portfolio of payload.portfolios || []) {
        for (const item of portfolio.symbols || []) {
          rows.push({ ...item, portfolio_id: portfolio.id, portfolio_name: portfolio.name });
        }
      }
    }
    function selectedRows() {
      if (currentFilter === "up") return rows.filter((item) => rateClass(item) === "up").sort((a, b) => rateNumber(b) - rateNumber(a));
      if (currentFilter === "down") return rows.filter((item) => rateClass(item) === "down").sort((a, b) => rateNumber(a) - rateNumber(b));
      return rows.filter((item) => String(item.portfolio_id) === String(currentPortfolioId));
    }
    function renderTabs() {
      const upCount = rows.filter((item) => rateClass(item) === "up").length;
      const downCount = rows.filter((item) => rateClass(item) === "down").length;
      els.upCount.textContent = upCount;
      els.downCount.textContent = downCount;
      els.filterTabs.innerHTML = "";
      for (const filter of [
        { id: "up", label: `5%以上上昇 (${upCount})` },
        { id: "down", label: `5%以下下落 (${downCount})` }
      ]) {
        const button = document.createElement("button");
        button.className = currentFilter === filter.id ? "active" : "";
        button.textContent = filter.label;
        button.addEventListener("click", () => { currentFilter = filter.id; render(); });
        els.filterTabs.appendChild(button);
      }
      els.portfolioTabs.innerHTML = "";
      for (const portfolio of payload.portfolios || []) {
        const button = document.createElement("button");
        button.className = currentFilter === "portfolio" && String(currentPortfolioId) === String(portfolio.id) ? "active" : "";
        button.textContent = `${portfolio.name} (${(portfolio.symbols || []).length})`;
        button.addEventListener("click", () => { currentFilter = "portfolio"; currentPortfolioId = portfolio.id; render(); });
        els.portfolioTabs.appendChild(button);
      }
    }
    function renderRows() {
      const items = selectedRows();
      els.empty.style.display = items.length ? "none" : "block";
      if (currentFilter === "up") els.sourceText.textContent = "全ポートフォリオ / 5%以上上昇";
      else if (currentFilter === "down") els.sourceText.textContent = "全ポートフォリオ / 5%以下下落";
      else {
        const portfolio = (payload.portfolios || []).find((item) => String(item.id) === String(currentPortfolioId));
        els.sourceText.textContent = portfolio ? `${portfolio.name} / ${portfolio.count_text}` : "";
      }
      els.rows.innerHTML = "";
      for (const item of items) {
        const kind = rateClass(item);
        const tr = document.createElement("tr");
        const price = item.price === "" || item.price === undefined ? "-" : `${yen.format(item.price)} ${item.currency || ""}`.trim();
        const cells = [item.symbol, item.portfolio_name, item.name, price, item.change || "-", item.rate || (item.error || "-"), judgeText(item)];
        for (const [index, value] of cells.entries()) {
          const td = document.createElement("td");
          td.textContent = value;
          if (index === 0) td.className = "symbol";
          if ([4, 5, 6].includes(index)) td.className = kind || (item.error && index >= 5 ? "error" : "muted");
          tr.appendChild(td);
        }
        els.rows.appendChild(tr);
      }
    }
    function render() {
      renderTabs();
      renderRows();
    }
    function uniqueSymbols() {
      const seen = new Set();
      const symbols = [];
      for (const portfolio of payload.portfolios || []) {
        for (const item of portfolio.symbols || []) {
          if (!item.symbol || seen.has(item.symbol)) continue;
          seen.add(item.symbol);
          symbols.push({ symbol: item.symbol, name: item.name });
        }
      }
      return symbols;
    }
    function formatChange(value) {
      const sign = value >= 0 ? "+" : "";
      return `${sign}${yen.format(value)}`;
    }
    function formatRate(value) {
      const sign = value >= 0 ? "+" : "";
      return `${sign}${value.toFixed(2)}%`;
    }
    function alertDirection(item) {
      if (typeof item.change_percent !== "number") return null;
      const up = Number(item.up_threshold_percent ?? payload.default_up_threshold_percent);
      const down = Number(item.down_threshold_percent ?? payload.default_down_threshold_percent);
      if (item.change_percent >= up) return "up";
      if (item.change_percent <= down) return "down";
      return null;
    }
    async function fetchLiveQuote(symbol) {
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=5d&interval=1d&_=${Date.now()}`;
      const data = await fetch(url, { cache: "no-store" }).then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      });
      const result = data.chart?.result?.[0];
      if (!result) throw new Error("データなし");
      const meta = result.meta || {};
      const closes = (result.indicators?.quote?.[0]?.close || []).filter((value) => value !== null && value !== undefined);
      let price = meta.regularMarketPrice;
      let previousClose = closes.length >= 2 ? closes[closes.length - 2] : (meta.previousClose || meta.chartPreviousClose);
      if ((price === null || price === undefined) && closes.length) price = closes[closes.length - 1];
      if (price === null || price === undefined || !previousClose) throw new Error("価格取得失敗");
      price = Number(price);
      previousClose = Number(previousClose);
      const change = price - previousClose;
      const changePercent = change / previousClose * 100;
      return {
        price,
        previous_close: previousClose,
        change,
        change_text: formatChange(change),
        rate: formatRate(changePercent),
        change_percent: changePercent,
        currency: meta.currency || ""
      };
    }
    async function refreshLiveQuotes() {
      const symbols = uniqueSymbols();
      const quotes = new Map();
      const batchSize = 8;
      let done = 0;
      for (let index = 0; index < symbols.length; index += batchSize) {
        const batch = symbols.slice(index, index + batchSize);
        await Promise.all(batch.map(async (item) => {
          try {
            quotes.set(item.symbol, await fetchLiveQuote(item.symbol));
          } catch (error) {
            quotes.set(item.symbol, { error: String(error).replace(/^Error: /, "") });
          } finally {
            done += 1;
          }
        }));
        els.statusText.textContent = `Yahooから更新中: ${done}/${symbols.length}`;
      }
      for (const portfolio of payload.portfolios || []) {
        for (const item of portfolio.symbols || []) {
          const quote = quotes.get(item.symbol);
          if (!quote) continue;
          if (quote.error) {
            item.error = quote.error;
            continue;
          }
          item.price = quote.price;
          item.previous_close = quote.previous_close;
          item.change = quote.change_text;
          item.rate = quote.rate;
          item.change_percent = quote.change_percent;
          item.currency = quote.currency || item.currency || "";
          item.alert_direction = alertDirection(item);
          item.error = "";
        }
      }
      payload.generated_at = new Date().toISOString();
    }
    async function refreshData() {
      if (!els.password.value) return;
      const previousFilter = currentFilter;
      const previousPortfolioId = currentPortfolioId;
      els.refreshButton.disabled = true;
      els.statusText.textContent = "更新中";
      try {
        await refreshLiveQuotes();
        buildRows();
        currentFilter = previousFilter || "portfolio";
        currentPortfolioId = (payload.portfolios || []).some((portfolio) => String(portfolio.id) === String(previousPortfolioId))
          ? previousPortfolioId
          : (payload.portfolios?.[0]?.id ?? null);
        els.statusText.textContent = `リアルタイム更新: ${new Date(payload.generated_at).toLocaleString("ja-JP")}`;
        render();
      } catch (error) {
        els.statusText.textContent = "更新失敗";
      } finally {
        els.refreshButton.disabled = false;
      }
    }
    async function unlock() {
      els.unlockButton.disabled = true;
      els.gateError.hidden = true;
      els.refreshButton.disabled = true;
      els.statusText.textContent = "確認中";
      try {
        payload = await decryptData(els.password.value);
        buildRows();
        currentPortfolioId = payload.portfolios?.[0]?.id ?? null;
        els.gate.hidden = true;
        els.app.hidden = false;
        els.refreshButton.disabled = false;
        els.statusText.textContent = `最終更新: ${new Date(payload.generated_at).toLocaleString("ja-JP")}`;
        render();
      } catch (error) {
        els.gateError.hidden = false;
        els.statusText.textContent = "パスワード未入力";
      } finally {
        els.unlockButton.disabled = false;
      }
    }
    els.unlockButton.addEventListener("click", unlock);
    els.refreshButton.addEventListener("click", refreshData);
    els.password.addEventListener("keydown", (event) => { if (event.key === "Enter") unlock(); });
  </script>
</body>
</html>
"""


def main() -> None:
    DOCS_DIR.mkdir(exist_ok=True)
    INDEX_PATH.write_text(HTML, encoding="utf-8")
    print(INDEX_PATH)


if __name__ == "__main__":
    main()
