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
    .metric, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
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
      .table-scroll { overflow-x: visible; }
      table { min-width: 0; table-layout: fixed; }
      th, td { padding: 10px 6px; font-size: 12px; line-height: 1.35; }
      th:nth-child(7), td:nth-child(7) { display: none; }
      th:nth-child(1), td:nth-child(1) { width: 15%; }
      th:nth-child(2), td:nth-child(2) { width: 14%; }
      th:nth-child(3), td:nth-child(3) { width: 26%; }
      th:nth-child(4), td:nth-child(4) { width: 15%; }
      th:nth-child(5), td:nth-child(5) { width: 15%; }
      th:nth-child(6), td:nth-child(6) { width: 15%; }
      th:nth-child(1), th:nth-child(2),
      th:nth-child(4), th:nth-child(5), th:nth-child(6) { font-size: 10px; }
      td:nth-child(3) {
        word-break: keep-all;
        overflow-wrap: anywhere;
      }
      td:nth-child(1), td:nth-child(2),
      td:nth-child(4), td:nth-child(5), td:nth-child(6) {
        word-break: break-word;
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
        <div class="muted" id="statusText">読み込み中</div>
      </div>
    </div>
  </header>
  <main class="wrap">
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
    const LIVE_PROXY_URL = "https://script.google.com/macros/s/AKfycbyy0_1l7yyb_OGl3yvRO5cVow5fueYN92QPUKnIT7RUycFQUYF-OTTy0QOp_uSQ-J0TOA/exec";
    const els = {
      app: document.querySelector("#app"),
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
    async function loadPublishedData() {
      const response = await fetch(`data.json?v=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`公開データ取得失敗: ${response.status}`);
      return response.json();
    }
    function rateNumber(item) {
      if (item.error) return 0;
      if (typeof item.change_percent === "number") return item.change_percent;
      return Number(String(item.rate || "").replace("%", "").replace("+", "")) || 0;
    }
    function rateClass(item) {
      if (item.error) return "";
      if (item.alert_direction === "up" || rateNumber(item) >= Number(payload.default_up_threshold_percent)) return "up";
      if (item.alert_direction === "down" || rateNumber(item) <= Number(payload.default_down_threshold_percent)) return "down";
      return "";
    }
    function judgeText(item) {
      if (item.error) return item.price === "" || item.price === undefined ? "取得失敗" : "取得失敗（前回値）";
      const kind = rateClass(item);
      if (kind === "up") return "値上がり通知対象";
      if (kind === "down") return "値下がり通知対象";
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
    function mergeYahooPortfolioSnapshot(snapshot) {
      const existingBySymbol = new Map();
      for (const portfolio of payload.portfolios || []) {
        for (const item of portfolio.symbols || []) {
          if (!existingBySymbol.has(item.symbol)) existingBySymbol.set(item.symbol, item);
        }
      }
      const previousSymbols = new Set(existingBySymbol.keys());
      const nextSymbols = new Set();
      const addedSymbols = [];
      payload.portfolios = (snapshot.portfolios || []).map((portfolio) => {
        const symbols = (portfolio.symbols || []).map((item) => {
          const base = existingBySymbol.get(item.symbol) || {
            price: "", previous_close: "", change: "", rate: "", change_percent: null,
            currency: "", quote_time: "", alert_direction: null, error: ""
          };
          if (!previousSymbols.has(item.symbol) && !nextSymbols.has(item.symbol)) {
            addedSymbols.push({ symbol: item.symbol, name: item.name || item.symbol });
          }
          nextSymbols.add(item.symbol);
          return { ...base, ...item, name: item.name || base.name || item.symbol };
        });
        return { ...portfolio, count_text: `${symbols.length}件`, symbols };
      });
      payload.portfolio_source = snapshot.source || "Yahooファイナンス ポートフォリオ";
      payload.portfolio_fetched_at = snapshot.fetched_at || "";
      return {
        addedSymbols,
        added: addedSymbols.length,
        removed: [...previousSymbols].filter((symbol) => !nextSymbols.has(symbol)).length,
        syncStatus: snapshot.sync_status || "live",
        syncError: snapshot.sync_error || ""
      };
    }
    async function syncYahooPortfolioList() {
      if (!LIVE_PROXY_URL) throw new Error("Yahoo同期中継未設定");
      const snapshot = await fetchJsonp(LIVE_PROXY_URL, { action: "portfolios", sync: "1" });
      if (!Array.isArray(snapshot.portfolios) || !snapshot.portfolios.length) {
        throw new Error(snapshot.sync_error || "Yahooポートフォリオ取得失敗");
      }
      const result = mergeYahooPortfolioSnapshot(snapshot);
      buildRows();
      if (!(payload.portfolios || []).some((portfolio) => String(portfolio.id) === String(currentPortfolioId))) {
        currentPortfolioId = snapshot.default_portfolio_id ?? payload.portfolios?.[0]?.id ?? null;
        currentFilter = "portfolio";
      }
      render();
      return result;
    }
    function formatChange(value) {
      const sign = value >= 0 ? "+" : "";
      return `${sign}${yen.format(value)}`;
    }
    function formatRate(value) {
      const sign = value >= 0 ? "+" : "";
      return `${sign}${value.toFixed(2)}%`;
    }
    function normalizeQuote(quote) {
      const price = Number(quote.price);
      const previousClose = Number(quote.previous_close);
      if (!Number.isFinite(price) || !Number.isFinite(previousClose) || previousClose === 0) {
        throw new Error("価格または前日終値が不正です");
      }
      const change = price - previousClose;
      const calculatedPercent = change / previousClose * 100;
      const sourcePercent = Number(quote.change_percent);
      const changePercent = Number.isFinite(sourcePercent) && Math.abs(sourcePercent - calculatedPercent) < 0.05
        ? sourcePercent
        : calculatedPercent;
      return {
        ...quote,
        price,
        previous_close: previousClose,
        change,
        change_percent: changePercent,
        change_text: formatChange(change),
        rate: formatRate(changePercent)
      };
    }
    function formatDateTime(value) {
      if (!value) return "";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return "";
      return date.toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" });
    }
    function alertDirection(item) {
      if (typeof item.change_percent !== "number") return null;
      const up = Number(item.up_threshold_percent ?? payload.default_up_threshold_percent);
      const down = Number(item.down_threshold_percent ?? payload.default_down_threshold_percent);
      if (item.change_percent >= up) return "up";
      if (item.change_percent <= down) return "down";
      return null;
    }
    function fetchJsonp(url, params) {
      return new Promise((resolve, reject) => {
        const callbackName = `liveQuotes_${Date.now()}_${Math.floor(Math.random() * 100000)}`;
        const script = document.createElement("script");
        const timeout = window.setTimeout(() => {
          cleanup();
          reject(new Error("中継タイムアウト"));
        }, 90000);
        function cleanup() {
          window.clearTimeout(timeout);
          delete window[callbackName];
          script.remove();
        }
        window[callbackName] = (data) => {
          cleanup();
          resolve(data);
        };
        const search = new URLSearchParams({ ...params, callback: callbackName, t: String(Date.now()) });
        script.src = `${url}?${search.toString()}`;
        script.onerror = () => {
          cleanup();
          reject(new Error("中継に接続できません"));
        };
        document.head.appendChild(script);
      });
    }
    async function refreshLiveQuotes(symbolsOverride) {
      if (!LIVE_PROXY_URL) throw new Error("リアルタイム中継未設定");
      const symbols = symbolsOverride || uniqueSymbols();
      if (!symbols.length) {
        return { success: 0, failed: 0, total: 0, quote_time: payload.quote_time || payload.generated_at };
      }
      const quotes = new Map();
      const batchSize = 10;
      let done = 0;
      let success = 0;
      let failed = 0;
      let newestQuoteTime = "";
      let newestJapanQuoteTime = "";
      for (let index = 0; index < symbols.length; index += batchSize) {
        const batch = symbols.slice(index, index + batchSize);
        let data = null;
        try {
          data = await fetchJsonp(LIVE_PROXY_URL, { symbols: batch.map((item) => item.symbol).join(",") });
        } catch (error) {
          data = { quotes: {} };
        }
        for (const item of batch) {
          let quote = data.quotes?.[item.symbol] || { error: "取得失敗" };
          if (!quote.error) {
            try {
              quote = normalizeQuote(quote);
            } catch (error) {
              quote = { error: error.message || "計算失敗" };
            }
          }
          if (!quote.error) {
            if (quote.quote_time && (!newestQuoteTime || new Date(quote.quote_time) > new Date(newestQuoteTime))) {
              newestQuoteTime = quote.quote_time;
            }
            if (
              (/\.(T|N|S|F)$/i.test(item.symbol) || /^[0-9A-Z]{8}$/i.test(item.symbol))
              && quote.quote_time
              && (!newestJapanQuoteTime || new Date(quote.quote_time) > new Date(newestJapanQuoteTime))
            ) {
              newestJapanQuoteTime = quote.quote_time;
            }
            success += 1;
          } else {
            failed += 1;
          }
          quotes.set(item.symbol, quote);
        }
        done += batch.length;
        els.statusText.textContent = `リアルタイム取得中: ${done}/${symbols.length} / OK ${success} / 失敗 ${failed}`;
        if (index + batchSize < symbols.length) {
          await new Promise((resolve) => window.setTimeout(resolve, 500));
        }
      }
      for (const portfolio of payload.portfolios || []) {
        for (const item of portfolio.symbols || []) {
          const quote = quotes.get(item.symbol);
          if (!quote) continue;
          if (quote.error) {
            item.error = quote.error;
            item.change_percent = null;
            item.alert_direction = null;
            continue;
          }
          item.price = quote.price;
          item.previous_close = quote.previous_close;
          item.change = quote.change_text;
          item.rate = quote.rate;
          item.change_percent = quote.change_percent;
          item.currency = quote.currency || item.currency || "";
          item.quote_time = quote.quote_time || "";
          item.market_state = quote.market_state || "";
          item.alert_direction = alertDirection(item);
          item.error = "";
        }
      }
      payload.generated_at = new Date().toISOString();
      payload.quote_time = newestJapanQuoteTime || newestQuoteTime || payload.quote_time || payload.generated_at;
      return { success, failed, total: symbols.length, quote_time: payload.quote_time };
    }
    async function refreshData() {
      const previousFilter = currentFilter;
      const previousPortfolioId = currentPortfolioId;
      els.refreshButton.disabled = true;
      els.statusText.textContent = LIVE_PROXY_URL ? "Yahoo銘柄・タブ同期中" : "公開済み最新データを確認中";
      try {
        let portfolioSync = null;
        try {
          portfolioSync = await syncYahooPortfolioList();
        } catch (syncError) {
          portfolioSync = null;
        }
        els.statusText.textContent = "リアルタイム更新中";
        const liveResult = await refreshLiveQuotes();
        if (liveResult.success < 1) {
          throw new Error(`リアルタイム取得失敗: ${liveResult.success}/${liveResult.total}`);
        }
        buildRows();
        currentFilter = previousFilter || "portfolio";
        currentPortfolioId = (payload.portfolios || []).some((portfolio) => String(portfolio.id) === String(previousPortfolioId))
          ? previousPortfolioId
          : (payload.portfolios?.[0]?.id ?? null);
        const syncText = portfolioSync
          ? `Yahoo${portfolioSync.syncStatus === "live" ? "同期済み" : "前回同期"} / `
          : "Yahoo同期失敗 / ";
        els.statusText.textContent = `${syncText}株価時点（日本株）: ${formatDateTime(liveResult.quote_time || payload.quote_time)} / 更新: ${formatDateTime(payload.generated_at)} / OK ${liveResult.success} / 失敗 ${liveResult.failed}`;
        render();
      } catch (error) {
        try {
          if (!payload) payload = await loadPublishedData();
          buildRows();
          currentFilter = previousFilter || "portfolio";
          currentPortfolioId = (payload.portfolios || []).some((portfolio) => String(portfolio.id) === String(previousPortfolioId))
            ? previousPortfolioId
            : (payload.portfolios?.[0]?.id ?? null);
          els.statusText.textContent = LIVE_PROXY_URL
            ? `リアルタイム取得失敗 / 公開済みデータ: ${formatDateTime(payload.quote_time || payload.generated_at)}`
            : `公開済みデータ: ${formatDateTime(payload.quote_time || payload.generated_at)}`;
          render();
        } catch (fallbackError) {
          els.statusText.textContent = "更新失敗";
        }
      } finally {
        els.refreshButton.disabled = false;
      }
    }
    async function loadInitialData() {
      els.refreshButton.disabled = true;
      els.statusText.textContent = "読み込み中";
      try {
        payload = await loadPublishedData();
        buildRows();
        currentPortfolioId = payload.portfolios?.[0]?.id ?? null;
        els.app.hidden = false;
        els.statusText.textContent = `株価時点（日本株）: ${formatDateTime(payload.quote_time || payload.generated_at)}`;
        render();
        els.statusText.textContent = "Yahoo銘柄・タブ同期中";
        try {
          const portfolioSync = await syncYahooPortfolioList();
          let addedResult = null;
          if (portfolioSync.addedSymbols.length) {
            els.statusText.textContent = `新規銘柄の株価取得中: ${portfolioSync.addedSymbols.length}件`;
            addedResult = await refreshLiveQuotes(portfolioSync.addedSymbols);
            buildRows();
            render();
          }
          const changeText = portfolioSync.added || portfolioSync.removed
            ? ` / 追加 ${portfolioSync.added} / 削除 ${portfolioSync.removed}`
            : "";
          const quoteText = addedResult ? ` / 新規株価 OK ${addedResult.success} / 失敗 ${addedResult.failed}` : "";
          els.statusText.textContent = `Yahoo${portfolioSync.syncStatus === "live" ? "同期済み" : "前回同期リスト"}${changeText}${quoteText} / 株価時点（日本株）: ${formatDateTime(payload.quote_time || payload.generated_at)}`;
        } catch (syncError) {
          els.statusText.textContent = `Yahoo同期未設定または期限切れ / 公開済みリスト / 株価時点（日本株）: ${formatDateTime(payload.quote_time || payload.generated_at)}`;
        }
        els.refreshButton.disabled = false;
      } catch (error) {
        els.statusText.textContent = "データ読み込み失敗";
      }
    }
    els.refreshButton.addEventListener("click", refreshData);
    loadInitialData();
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
