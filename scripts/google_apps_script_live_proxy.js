const MAX_SYMBOLS = 400;
const YAHOO_COOKIE_PROPERTY = "YAHOO_COOKIE";
const PORTFOLIO_CACHE_PREFIX = "YAHOO_PORTFOLIO_CACHE_";
const PORTFOLIO_CACHE_CHUNK_SIZE = 8000;

function doGet(e) {
  const params = e && e.parameter ? e.parameter : {};
  const callback = String(params.callback || "");
  const action = String(params.action || "quotes");

  if (action === "portfolios") {
    return outputPayload(portfolioResponse(params), callback);
  }
  if (action === "session_status") {
    const configured = Boolean(PropertiesService.getScriptProperties().getProperty(YAHOO_COOKIE_PROPERTY));
    return outputPayload({ configured: configured }, callback);
  }

  const symbols = String(params.symbols || "")
    .split(",")
    .map((symbol) => symbol.trim())
    .filter(Boolean)
    .slice(0, MAX_SYMBOLS);

  const payload = {
    generated_at: new Date().toISOString(),
    quote_time: "",
    success: 0,
    total: symbols.length,
    quotes: {},
  };

  const quotes = fetchQuotes(symbols);
  for (const symbol of symbols) {
    payload.quotes[symbol] = quotes[symbol] || { error: "取得失敗" };
    if (!payload.quotes[symbol].error) {
      if (
        payload.quotes[symbol].quote_time
        && (!payload.quote_time || new Date(payload.quotes[symbol].quote_time) > new Date(payload.quote_time))
      ) {
        payload.quote_time = payload.quotes[symbol].quote_time;
      }
      payload.success += 1;
    }
  }

  return outputPayload(payload, callback);
}

function outputPayload(payload, callback) {
  const json = JSON.stringify(payload);
  if (/^[A-Za-z_$][0-9A-Za-z_$]*(\.[A-Za-z_$][0-9A-Za-z_$]*)*$/.test(callback)) {
    return ContentService
      .createTextOutput(callback + "(" + json + ");")
      .setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return ContentService
    .createTextOutput(json)
    .setMimeType(ContentService.MimeType.JSON);
}

function portfolioResponse(params) {
  const shouldSync = String(params.sync || "1") !== "0";
  let syncError = "";
  if (shouldSync) {
    try {
      const livePayload = syncYahooPortfolios();
      savePortfolioCache(livePayload);
      return Object.assign({ sync_status: "live", sync_error: "" }, livePayload);
    } catch (error) {
      syncError = cleanError(error);
    }
  }

  const cached = loadPortfolioCache();
  if (cached && Array.isArray(cached.portfolios)) {
    return Object.assign({ sync_status: "cached", sync_error: syncError }, cached);
  }
  return {
    sync_status: "unavailable",
    sync_error: syncError || "Yahoo同期データがありません",
    fetched_at: "",
    default_portfolio_id: null,
    portfolios: [],
  };
}

function syncYahooPortfolios() {
  const cookie = PropertiesService.getScriptProperties().getProperty(YAHOO_COOKIE_PROPERTY);
  if (!cookie) throw new Error("Yahooセッション未設定");

  const firstHtml = fetchYahooPortfolioPage(1, cookie);
  const links = parseYahooPortfolioLinks(firstHtml);
  if (!links.length) throw new Error("Yahooポートフォリオ一覧取得失敗");

  const requests = links.map((portfolio) => ({
    url: yahooPortfolioUrl(portfolio.id),
    muteHttpExceptions: true,
    followRedirects: true,
    headers: yahooPortfolioHeaders(cookie),
  }));
  const responses = UrlFetchApp.fetchAll(requests);
  const portfolios = [];
  for (let index = 0; index < links.length; index += 1) {
    const response = responses[index];
    if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
      throw new Error("Yahooポートフォリオ HTTP " + response.getResponseCode());
    }
    const html = response.getContentText("UTF-8");
    if (isYahooLoginPage(html)) throw new Error("Yahooセッション期限切れ");
    const symbols = parseYahooPortfolioRows(html);
    portfolios.push({
      id: links[index].id,
      name: links[index].name,
      url: yahooPortfolioUrl(links[index].id),
      count_text: symbols.length + "件",
      as_of: new Date().toISOString(),
      symbols: symbols,
    });
  }

  return {
    source: "Yahooファイナンス ポートフォリオ（クラウド同期）",
    fetched_at: new Date().toISOString(),
    default_portfolio_id: portfolios.length ? portfolios[0].id : null,
    portfolios: portfolios,
  };
}

function fetchYahooPortfolioPage(portfolioId, cookie) {
  const response = UrlFetchApp.fetch(yahooPortfolioUrl(portfolioId), {
    muteHttpExceptions: true,
    followRedirects: true,
    headers: yahooPortfolioHeaders(cookie),
  });
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
    throw new Error("Yahooポートフォリオ HTTP " + response.getResponseCode());
  }
  const html = response.getContentText("UTF-8");
  if (isYahooLoginPage(html)) throw new Error("Yahooセッション期限切れ");
  return html;
}

function yahooPortfolioUrl(portfolioId) {
  return "https://finance.yahoo.co.jp/portfolio/detail?portfolioId=" + encodeURIComponent(portfolioId) + "&_=" + Date.now();
}

function yahooPortfolioHeaders(cookie) {
  return {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Cookie": cookie,
  };
}

function isYahooLoginPage(html) {
  const text = String(html || "");
  return text.includes("ログインするため")
    || text.includes("確認コードを送信")
    || text.includes("別のYahoo! JAPAN IDでログイン");
}

function normalizeYahooHtml(html) {
  return String(html || "")
    .replace(/\\u0026/gi, "&")
    .replace(/\\u003d/gi, "=")
    .replace(/\\u002f/gi, "/")
    .replace(/\\\//g, "/");
}

function parseYahooPortfolioLinks(html) {
  const source = normalizeYahooHtml(html);
  const portfolios = [];
  const seen = {};
  const pattern = /<a\b[^>]*href=(["'])([^"']*\/portfolio\/detail\?[^"']*portfolioId=(\d+)[^"']*)\1[^>]*>([\s\S]*?)<\/a>/gi;
  let match;
  while ((match = pattern.exec(source)) !== null) {
    const id = Number(match[3]);
    const name = stripHtml(match[4]);
    if (!id || !name || seen[id]) continue;
    seen[id] = true;
    portfolios.push({ id: id, name: name });
  }
  return portfolios;
}

function parseYahooPortfolioRows(html) {
  const source = normalizeYahooHtml(html);
  const symbols = [];
  const seen = {};
  const rowPattern = /<tr\b[^>]*>([\s\S]*?)<\/tr>/gi;
  let rowMatch;
  while ((rowMatch = rowPattern.exec(source)) !== null) {
    const row = rowMatch[1];
    const hrefMatch = row.match(/\/quote\/([^"'/?#<\\]+)/i);
    if (!hrefMatch) continue;
    let symbol = decodeURIComponent(hrefMatch[1]);
    symbol = symbol.replace(/&amp;.*$/, "").trim();
    if (!symbol || seen[symbol]) continue;
    const linkMatch = row.match(/<a\b[^>]*href=(["'])[^"']*\/quote\/[^"']+\1[^>]*>([\s\S]*?)<\/a>/i);
    const name = linkMatch ? stripHtml(linkMatch[2]) : symbol;
    seen[symbol] = true;
    symbols.push({ symbol: symbol, name: name || symbol });
  }
  return symbols;
}

function stripHtml(value) {
  return decodeHtml(String(value || "")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " "))
    .replace(/\s+/g, " ")
    .trim();
}

function savePortfolioCache(payload) {
  const properties = PropertiesService.getScriptProperties();
  const text = JSON.stringify(payload);
  const chunks = [];
  for (let index = 0; index < text.length; index += PORTFOLIO_CACHE_CHUNK_SIZE) {
    chunks.push(text.slice(index, index + PORTFOLIO_CACHE_CHUNK_SIZE));
  }
  const previousCount = Number(properties.getProperty(PORTFOLIO_CACHE_PREFIX + "COUNT") || 0);
  const values = {};
  values[PORTFOLIO_CACHE_PREFIX + "COUNT"] = String(chunks.length);
  for (let index = 0; index < chunks.length; index += 1) {
    values[PORTFOLIO_CACHE_PREFIX + index] = chunks[index];
  }
  properties.setProperties(values, false);
  for (let index = chunks.length; index < previousCount; index += 1) {
    properties.deleteProperty(PORTFOLIO_CACHE_PREFIX + index);
  }
}

function loadPortfolioCache() {
  const properties = PropertiesService.getScriptProperties();
  const count = Number(properties.getProperty(PORTFOLIO_CACHE_PREFIX + "COUNT") || 0);
  if (!count) return null;
  let text = "";
  for (let index = 0; index < count; index += 1) {
    const chunk = properties.getProperty(PORTFOLIO_CACHE_PREFIX + index);
    if (chunk === null) return null;
    text += chunk;
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    return null;
  }
}

function cleanError(error) {
  return String(error || "取得失敗").replace(/^Error: /, "");
}

function safeFetchAll(requests) {
  try {
    return UrlFetchApp.fetchAll(requests);
  } catch (error) {
    return requests.map(() => ({
      getResponseCode: () => 599,
      getContentText: () => "",
    }));
  }
}

function fetchQuotes(symbols) {
  const quotes = {};
  const japanSymbols = symbols.filter(isYahooJapanQuoteSymbol);
  const otherSymbols = symbols.filter((symbol) => !isYahooJapanQuoteSymbol(symbol));

  const japanRequests = japanSymbols.map((symbol) => ({
    url: yahooJapanQuoteUrl(symbol),
    muteHttpExceptions: true,
    headers: {
      "User-Agent": "Mozilla/5.0",
      "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
      "Cache-Control": "no-cache",
      "Pragma": "no-cache",
    },
  }));

  if (japanRequests.length) {
    const responses = safeFetchAll(japanRequests);
    for (let index = 0; index < japanSymbols.length; index += 1) {
      const symbol = japanSymbols[index];
      const response = responses[index];
      try {
        if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
          throw new Error("Yahoo日本版 HTTP " + response.getResponseCode());
        }
        quotes[symbol] = parseYahooJapanQuote(symbol, response.getContentText("UTF-8"));
        if (!quotes[symbol].quote_time) throw new Error("株価日付を確認できません");
      } catch (error) {
        quotes[symbol] = { error: String(error).replace(/^Error: /, "") };
      }
    }
  }

  const sessionAlignedQuotes = fetchQuotesFromDailyChart(japanSymbols.filter(isJapanMarketSymbol));
  for (const symbol of Object.keys(sessionAlignedQuotes)) {
    if (!sessionAlignedQuotes[symbol].error) quotes[symbol] = sessionAlignedQuotes[symbol];
  }

  try {
    Object.assign(quotes, fetchQuotesFromQuoteApi(otherSymbols));
  } catch (error) {
    // The per-symbol chart fallback below can still succeed.
  }

  for (const symbol of otherSymbols) {
    if (quotes[symbol] && !quotes[symbol].error) continue;
    try {
      quotes[symbol] = fetchQuoteFromChart(symbol);
    } catch (error) {
      quotes[symbol] = { error: String(error).replace(/^Error: /, "") };
    }
  }

  for (const symbol of japanSymbols) {
    if (quotes[symbol] && !quotes[symbol].error) continue;
    try {
      quotes[symbol] = fetchQuoteFromYahooJapanHistory(symbol);
    } catch (error) {
      quotes[symbol] = { error: String(error).replace(/^Error: /, "") };
    }
  }

  return quotes;
}

function fetchQuote(symbol) {
  if (isJapanMarketSymbol(symbol)) {
    try {
      return fetchQuoteFromDailyChart(symbol);
    } catch (error) {
      try {
        const quote = fetchQuoteFromYahooJapan(symbol);
        if (!quote.quote_time) throw new Error("株価日付を確認できません");
        return quote;
      } catch (pageError) {
        return fetchQuoteFromYahooJapanHistory(symbol);
      }
    }
  }
  try {
    return fetchQuoteFromYahooJapan(symbol);
  } catch (error) {
    if (isYahooJapanQuoteSymbol(symbol)) return fetchQuoteFromYahooJapanHistory(symbol);
  }
  return fetchQuoteFromChart(symbol);
}

function isJapanMarketSymbol(symbol) {
  return /\.(T|N|S|F)$/i.test(symbol);
}

function isYahooJapanQuoteSymbol(symbol) {
  return isJapanMarketSymbol(symbol) || /^[0-9A-Z]{8}$/i.test(symbol);
}

function fetchQuoteFromYahooJapan(symbol) {
  const url = yahooJapanQuoteUrl(symbol);
  const response = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: {
      "User-Agent": "Mozilla/5.0",
      "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
      "Cache-Control": "no-cache",
      "Pragma": "no-cache",
    },
  });
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
    throw new Error("Yahoo日本版 HTTP " + response.getResponseCode());
  }

  return parseYahooJapanQuote(symbol, response.getContentText("UTF-8"));
}

function fetchQuoteFromYahooJapanHistory(symbol) {
  const response = UrlFetchApp.fetch(
    "https://finance.yahoo.co.jp/quote/" + encodeURIComponent(symbol) + "/history?_=" + Date.now(),
    {
      muteHttpExceptions: true,
      headers: {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
      },
    }
  );
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
    throw new Error("Yahoo日本版時系列 HTTP " + response.getResponseCode());
  }
  return parseYahooJapanHistoryQuote(symbol, response.getContentText("UTF-8"));
}

function parseYahooJapanHistoryQuote(symbol, html, now = new Date()) {
  const byDate = new Map();
  let closeIndex = isJapanMarketSymbol(symbol) ? 4 : -1;
  for (const match of String(html).matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)) {
    const cells = [...match[1].matchAll(/<t[dh]\b[^>]*>([\s\S]*?)<\/t[dh]>/gi)]
      .map((cell) => stripHtml(cell[1]));
    if (cells[0] === "日付") {
      closeIndex = cells.findIndex((cell) => cell === "終値" || cell === "基準価額");
      continue;
    }
    if (!/^20[0-9]{2}\/[0-1]?[0-9]\/[0-3]?[0-9]$/.test(cells[0] || "")) continue;
    const parts = cells[0].split("/");
    const date = parts.map((part, i) => part.padStart(i ? 2 : 4, "0")).join("-");
    if (new Date(date + "T15:30:00+09:00") > now) continue;
    if (closeIndex < 0 || !/^[0-9][0-9,]*(?:\.[0-9]+)?$/.test(cells[closeIndex] || "")) {
      throw new Error("時系列の終値が欠損しています");
    }
    byDate.set(date, { date, close: parseNumber(cells[closeIndex]) });
  }
  const rows = [...byDate.values()].sort((a, b) => b.date.localeCompare(a.date));
  if (rows.length < 2) throw new Error("Yahoo日本版時系列不足");
  const dateParts = rows[0].date.split("-").map(Number);
  const quoteTime = new Date(
    String(dateParts[0]).padStart(4, "0") + "-"
    + String(dateParts[1]).padStart(2, "0") + "-"
    + String(dateParts[2]).padStart(2, "0") + "T15:30:00+09:00"
  ).toISOString();
  const quote = quoteResult(rows[0].close, rows[1].close, null, "JPY", quoteTime, "CLOSED");
  quote.quote_session_date = rows[0].date.replace(/\//g, "-");
  quote.previous_close_session_date = rows[1].date.replace(/\//g, "-");
  quote.source = "yahoo_japan_history";
  quote.warning = "履歴終値（現在値の取得失敗時の参考値）";
  return quote;
}

function yahooJapanQuoteUrl(symbol) {
  return "https://finance.yahoo.co.jp/quote/" + encodeURIComponent(symbol) + "?_=" + Date.now();
}

function parseYahooJapanQuote(symbol, html) {
  const lines = htmlToLines(html);
  const changeIndex = lines.indexOf("前日比");
  if (changeIndex < 0) throw new Error("Yahoo日本版 前日比なし");

  let price = null;
  for (let index = changeIndex - 1; index >= 0; index -= 1) {
    if (/^[0-9][0-9,]*(?:\.[0-9]+)?$/.test(lines[index])) {
      price = parseNumber(lines[index]);
      break;
    }
  }

  let change = null;
  let changePercent = null;
  const changeLines = lines.slice(changeIndex + 1, changeIndex + 8);
  const joinedMatch = changeLines.join("").match(/^([+\-\u2212]?[0-9,]+(?:\.[0-9]+)?)\(([+\-\u2212]?[0-9.]+)%\)/);
  if (joinedMatch) {
    change = parseNumber(joinedMatch[1]);
    changePercent = parseNumber(joinedMatch[2]);
  }
  for (let index = changeIndex + 1; index < Math.min(lines.length, changeIndex + 8); index += 1) {
    if (change !== null && changePercent !== null) break;
    const combinedMatch = lines[index].match(/([+\-\u2212]?[0-9,]+(?:\.[0-9]+)?)\s*\(([+\-\u2212]?[0-9.]+)%\)/);
    if (combinedMatch) {
      change = parseNumber(combinedMatch[1]);
      changePercent = parseNumber(combinedMatch[2]);
      break;
    }
    if (change === null && /^[+\-\u2212][0-9,]+(?:\.[0-9]+)?$/.test(lines[index])) {
      change = parseNumber(lines[index]);
    }
    const percentMatch = lines[index].match(/\(([+\-\u2212]?[0-9.]+)%\)|^([+\-\u2212]?[0-9.]+)%$/);
    if (changePercent === null && percentMatch) {
      changePercent = parseNumber(percentMatch[1] || percentMatch[2]);
    }
  }

  if (price === null || change === null || changePercent === null) {
    throw new Error("Yahoo日本版 現在値取得失敗");
  }

  const previousClose = price - change;
  if (!Number.isFinite(previousClose) || previousClose <= 0) {
    throw new Error("Yahoo日本版 前日終値不正");
  }
  if (Math.abs(change / previousClose * 100 - changePercent) > 0.011) {
    throw new Error("Yahoo日本版の現在値と前日比が不整合です");
  }
  return quoteResult(price, previousClose, changePercent, "JPY", yahooJapanQuoteTime(lines), "");
}

function fetchQuoteFromChart(symbol) {
  const url = "https://query1.finance.yahoo.com/v8/finance/chart/"
    + encodeURIComponent(symbol)
    + "?range=1d&interval=1m&includePrePost=false";
  const response = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: { "User-Agent": "Mozilla/5.0" },
  });
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
    throw new Error("HTTP " + response.getResponseCode());
  }
  const data = JSON.parse(response.getContentText());
  const result = data.chart && data.chart.result && data.chart.result[0];
  if (!result) throw new Error("データなし");

  const meta = result.meta || {};
  const closes = (((result.indicators || {}).quote || [{}])[0].close || [])
    .filter((value) => value !== null && value !== undefined);

  let price = meta.regularMarketPrice;
  let previousClose = meta.chartPreviousClose || meta.previousClose;

  if ((price === null || price === undefined) && closes.length) {
    price = closes[closes.length - 1];
  }
  if (price === null || price === undefined || !previousClose) {
    throw new Error("価格取得失敗");
  }

  price = Number(price);
  previousClose = Number(previousClose);
  const quoteTime = meta.regularMarketTime
    ? new Date(Number(meta.regularMarketTime) * 1000).toISOString()
    : "";
  return quoteResult(price, previousClose, null, meta.currency || "", quoteTime, meta.marketState || "");
}

function fetchQuoteFromQuoteApi(symbol) {
  const quotes = fetchQuotesFromQuoteApi([symbol]);
  if (!quotes[symbol] || quotes[symbol].error) {
    throw new Error(quotes[symbol] ? quotes[symbol].error : "quote取得失敗");
  }
  return quotes[symbol];
}

function fetchQuotesFromQuoteApi(symbols) {
  const quotes = {};
  if (!symbols.length) return quotes;
  const joinedSymbols = symbols.join(",");
  const url = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=" + encodeURIComponent(joinedSymbols);
  const response = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: { "User-Agent": "Mozilla/5.0" },
  });
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
    for (const symbol of symbols) {
      quotes[symbol] = { error: "quote HTTP " + response.getResponseCode() };
    }
    return quotes;
  }
  const data = JSON.parse(response.getContentText());
  const items = data.quoteResponse && data.quoteResponse.result ? data.quoteResponse.result : [];
  const bySymbol = {};
  for (const item of items) bySymbol[item.symbol] = item;

  for (const symbol of symbols) {
    try {
      const item = bySymbol[symbol];
      if (!item) throw new Error("quoteデータなし");
      const price = Number(item.regularMarketPrice);
      const change = Number(item.regularMarketChange);
      const changePercent = Number(item.regularMarketChangePercent);
      let previousClose = Number(item.regularMarketPreviousClose);
      if (!previousClose && Number.isFinite(price) && Number.isFinite(change)) {
        previousClose = price - change;
      }
      if (!Number.isFinite(price) || !Number.isFinite(change) || !Number.isFinite(changePercent) || !previousClose) {
        throw new Error("quote価格取得失敗");
      }
      const quoteTime = item.regularMarketTime
        ? new Date(Number(item.regularMarketTime) * 1000).toISOString()
        : "";
      quotes[symbol] = quoteResult(price, previousClose, changePercent, item.currency || "JPY", quoteTime, item.marketState || "");
    } catch (error) {
      quotes[symbol] = { error: String(error).replace(/^Error: /, "") };
    }
  }
  return quotes;
}

function fetchQuoteFromDailyChart(symbol) {
  const url = "https://query1.finance.yahoo.com/v8/finance/chart/"
    + encodeURIComponent(symbol)
    + "?range=1mo&interval=1d&includePrePost=false";
  const response = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: { "User-Agent": "Mozilla/5.0" },
  });
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
    throw new Error("日足HTTP " + response.getResponseCode());
  }
  const data = JSON.parse(response.getContentText());
  const result = data.chart && data.chart.result && data.chart.result[0];
  if (!result) throw new Error("日足データなし");

  return quoteFromDailyChartResult(symbol, result);
}

function fetchQuotesFromDailyChart(symbols) {
  const quotes = {};
  if (!symbols.length) return quotes;
  const requests = symbols.map((symbol) => ({
    url: "https://query1.finance.yahoo.com/v8/finance/chart/"
      + encodeURIComponent(symbol)
      + "?range=1mo&interval=1d&includePrePost=false",
    muteHttpExceptions: true,
    headers: { "User-Agent": "Mozilla/5.0" },
  }));
  const responses = safeFetchAll(requests);
  for (let index = 0; index < symbols.length; index += 1) {
    const symbol = symbols[index];
    try {
      const response = responses[index];
      if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
        throw new Error("日足HTTP " + response.getResponseCode());
      }
      const data = JSON.parse(response.getContentText());
      const result = data.chart && data.chart.result && data.chart.result[0];
      if (!result) throw new Error("日足データなし");
      quotes[symbol] = quoteFromDailyChartResult(symbol, result);
    } catch (error) {
      quotes[symbol] = { error: String(error).replace(/^Error: /, "") };
    }
  }
  return quotes;
}

function sessionDateKey(timestampSeconds, utcOffsetSeconds) {
  const adjusted = new Date((Number(timestampSeconds) + Number(utcOffsetSeconds || 0)) * 1000);
  return adjusted.toISOString().slice(0, 10);
}

function dailyCloseEntries(result, symbol) {
  const meta = result.meta || {};
  const offset = Number(meta.gmtoffset || (isJapanMarketSymbol(symbol) ? 9 * 60 * 60 : 0));
  const timestamps = result.timestamp || [];
  const closes = (((result.indicators || {}).quote || [{}])[0].close || []);
  const entries = [];
  for (let index = 0; index < Math.min(timestamps.length, closes.length); index += 1) {
    let close = Number(closes[index]);
    if (closes[index] === null || closes[index] === undefined) continue;
    if (!Number.isFinite(close) || close <= 0) throw new Error("日足終値不正");
    close = Number(close.toFixed(Math.min(8, Math.max(0, Number(meta.priceHint ?? 6)))));
    const timestamp = Number(timestamps[index]);
    entries.push({ timestamp: timestamp, close: close, date: sessionDateKey(timestamp, offset) });
  }
  return entries.sort((left, right) => left.timestamp - right.timestamp);
}

function quoteFromDailyChartResult(symbol, result) {
  const meta = result.meta || {};
  const entries = dailyCloseEntries(result, symbol);
  if (entries.length < 2) throw new Error("日足終値不足");

  const offset = Number(meta.gmtoffset || (isJapanMarketSymbol(symbol) ? 9 * 60 * 60 : 0));
  const regularMarketTime = Number(meta.regularMarketTime);
  if (!Number.isFinite(regularMarketTime) || regularMarketTime <= 0) throw new Error("株価時刻なし");
  let quoteSessionDate = sessionDateKey(regularMarketTime, offset);
  const marketState = String(meta.marketState || "").toUpperCase();
  let price;
  let previousCandidates;
  let quoteTimestamp = regularMarketTime;

  if (!["CLOSED", "PRE", "PREPRE", "POST", "POSTPOST"].includes(marketState)) {
    price = Number(meta.regularMarketPrice);
    if (!Number.isFinite(price) || price <= 0) {
      const sameSession = entries.filter((entry) => entry.date === quoteSessionDate);
      if (!sameSession.length) throw new Error("取引中現在値なし");
      price = sameSession[sameSession.length - 1].close;
    }
    previousCandidates = entries.filter((entry) => entry.date < quoteSessionDate);
  } else {
    const completedSessions = entries.filter((entry) => entry.date === quoteSessionDate);
    if (!completedSessions.length) throw new Error("確定終値なし");
    const currentSession = completedSessions[completedSessions.length - 1];
    price = currentSession.close;
    if (meta.regularMarketPrice != null && Math.abs(Number(meta.regularMarketPrice) - price) > 0.011) {
      throw new Error("最終株価と日足終値が不整合です");
    }
    quoteSessionDate = currentSession.date;
    previousCandidates = entries.filter((entry) => entry.date < quoteSessionDate);
    if (sessionDateKey(regularMarketTime, offset) !== quoteSessionDate) {
      quoteTimestamp = currentSession.timestamp;
    }
  }

  if (!previousCandidates.length) throw new Error("前取引日終値なし");
  const previousSession = previousCandidates[previousCandidates.length - 1];
  const previousDates = (result.timestamp || []).map((ts) => sessionDateKey(ts, offset))
    .filter((date) => date < quoteSessionDate).sort();
  if (previousDates.length && previousDates[previousDates.length - 1] !== previousSession.date) {
    throw new Error("前取引日の終値が欠損しています");
  }
  const resultQuote = quoteResult(
    Number(price.toFixed(Math.min(8, Math.max(0, Number(meta.priceHint ?? 6))))),
    previousSession.close,
    null,
    meta.currency || "JPY",
    new Date(quoteTimestamp * 1000).toISOString(),
    marketState
  );
  resultQuote.quote_session_date = quoteSessionDate;
  resultQuote.previous_close_session_date = previousSession.date;
  resultQuote.source = "yahoo_daily_chart";
  return resultQuote;
}

function quoteResult(price, previousClose, suppliedChangePercent, currency, quoteTime, marketState) {
  if (typeof price === "boolean" || typeof previousClose === "boolean") throw new Error("価格不正");
  price = Number(price);
  previousClose = Number(previousClose);
  if (!Number.isFinite(price) || price <= 0 || !Number.isFinite(previousClose) || previousClose <= 0) {
    throw new Error("価格または前日終値が不正");
  }
  const change = price - previousClose;
  const changePercent = change / previousClose * 100;
  return {
    price: price,
    previous_close: previousClose,
    change: change,
    change_percent: changePercent,
    currency: currency || "",
    quote_time: quoteTime,
    market_state: marketState || "",
  };
}

function htmlToLines(html) {
  return decodeHtml(String(html || "")
    .replace(/<script[\s\S]*?<\/script>/gi, "\n")
    .replace(/<style[\s\S]*?<\/style>/gi, "\n")
    .replace(/<[^>]+>/g, "\n"))
    .split(/\n+/)
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean);
}

function decodeHtml(text) {
  return String(text || "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, "\"")
    .replace(/&#39;/g, "'")
    .replace(/&#x([0-9a-f]+);/gi, (_, hex) => String.fromCharCode(parseInt(hex, 16)))
    .replace(/&#([0-9]+);/g, (_, num) => String.fromCharCode(parseInt(num, 10)));
}

function parseNumber(value) {
  return Number(String(value || "")
    .replace(/,/g, "")
    .replace(/\+/g, "")
    .replace(/\u2212/g, "-")
    .replace(/[円％%]/g, "")
    .trim());
}

function yahooJapanQuoteTime(lines) {
  let priceLabelIndex = lines.indexOf("リアルタイム株価");
  if (priceLabelIndex < 0) priceLabelIndex = lines.indexOf("15分ディレイ株価");
  if (priceLabelIndex >= 0) {
    for (let index = priceLabelIndex + 1; index < Math.min(lines.length, priceLabelIndex + 5); index += 1) {
      const match = lines[index].match(/^([0-2]?[0-9]):([0-5][0-9])$/);
      if (match) {
        const quoteTime = todayJapanTimeIso(Number(match[1]), Number(match[2]));
        if (quoteTime) return quoteTime;
      }
      const dateMatch = lines[index].match(/^([0-1]?[0-9])\/([0-3]?[0-9])$/);
      if (dateMatch) return japanDateTimeIso(Number(dateMatch[1]), Number(dateMatch[2]), 15, 30);
    }
  }
  const changeIndex = lines.indexOf("前日比");
  if (changeIndex >= 0) {
    for (let index = changeIndex + 1; index < Math.min(lines.length, changeIndex + 12); index += 1) {
      const dateMatch = lines[index].match(/^([0-1]?[0-9])\/([0-3]?[0-9])$/);
      if (dateMatch) return japanDateTimeIso(Number(dateMatch[1]), Number(dateMatch[2]), 15, 30);
    }
  }
  return "";
}

function todayJapanTimeIso(hour, minute) {
  const now = new Date();
  const japan = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  if (japan.getUTCDay() === 0 || japan.getUTCDay() === 6 || japan.getUTCHours() < 9) return "";
  const date = [
    japan.getUTCFullYear(),
    String(japan.getUTCMonth() + 1).padStart(2, "0"),
    String(japan.getUTCDate()).padStart(2, "0"),
  ].join("-");
  let quoteTime = new Date(date + "T" + String(hour).padStart(2, "0") + ":" + String(minute).padStart(2, "0") + ":00+09:00");
  if (quoteTime.getTime() > now.getTime() + 10 * 60 * 1000) {
    return "";
  }
  return quoteTime.toISOString();
}

function japanDateTimeIso(month, day, hour, minute) {
  const now = new Date();
  const japan = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  let year = japan.getUTCFullYear();
  let quoteTime = new Date(
    year + "-"
    + String(month).padStart(2, "0") + "-"
    + String(day).padStart(2, "0") + "T"
    + String(hour).padStart(2, "0") + ":"
    + String(minute).padStart(2, "0") + ":00+09:00"
  );
  if (month > japan.getUTCMonth() + 1 || (month === japan.getUTCMonth() + 1 && day > japan.getUTCDate())) {
    year -= 1;
    quoteTime = new Date(
      year + "-"
      + String(month).padStart(2, "0") + "-"
      + String(day).padStart(2, "0") + "T"
      + String(hour).padStart(2, "0") + ":"
      + String(minute).padStart(2, "0") + ":00+09:00"
    );
  }
  return quoteTime > now ? "" : quoteTime.toISOString();
}
