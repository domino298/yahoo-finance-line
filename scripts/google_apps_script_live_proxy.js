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
  if (!payload.quote_time) payload.quote_time = payload.generated_at;

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

function fetchQuotes(symbols) {
  const quotes = {};
  const fallbackSymbols = [];
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
    const responses = UrlFetchApp.fetchAll(japanRequests);
    for (let index = 0; index < japanSymbols.length; index += 1) {
      const symbol = japanSymbols[index];
      const response = responses[index];
      try {
        if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
          throw new Error("Yahoo日本版 HTTP " + response.getResponseCode());
        }
        quotes[symbol] = parseYahooJapanQuote(symbol, response.getContentText("UTF-8"));
      } catch (error) {
        fallbackSymbols.push(symbol);
      }
    }
  }

  const quoteApiSymbols = fallbackSymbols.concat(otherSymbols);
  Object.assign(quotes, fetchQuotesFromQuoteApi(quoteApiSymbols));

  for (const symbol of quoteApiSymbols) {
    if (quotes[symbol] && !quotes[symbol].error) continue;
    try {
      quotes[symbol] = isJapanMarketSymbol(symbol) ? fetchQuoteFromDailyChart(symbol) : fetchQuoteFromChart(symbol);
    } catch (error) {
      quotes[symbol] = { error: String(error).replace(/^Error: /, "") };
    }
  }

  return quotes;
}

function fetchQuote(symbol) {
  try {
    return fetchQuoteFromYahooJapan(symbol);
  } catch (error) {
    // Yahoo!ファイナンス日本版を優先し、取れない時だけ別ルートへ戻します。
  }
  if (isJapanMarketSymbol(symbol)) {
    try {
      return fetchQuoteFromQuoteApi(symbol);
    } catch (error) {
      // quote APIも取れない時は日足で最後に確認します。
    }
    return fetchQuoteFromDailyChart(symbol);
  }
  return fetchQuoteFromChart(symbol);
}

function isJapanMarketSymbol(symbol) {
  return /\.(T|N|S|F)$/.test(symbol);
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
  return quoteResult(price, previousClose, changePercent, "JPY", yahooJapanQuoteTime(lines), "REGULAR");
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
  if ((previousClose === null || previousClose === undefined) && closes.length >= 2) {
    previousClose = closes[closes.length - 2];
  }
  if (price === null || price === undefined || !previousClose) {
    throw new Error("価格取得失敗");
  }

  price = Number(price);
  previousClose = Number(previousClose);
  const quoteTime = meta.regularMarketTime
    ? new Date(Number(meta.regularMarketTime) * 1000).toISOString()
    : new Date().toISOString();
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
        : new Date().toISOString();
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
    + "?range=10d&interval=1d&includePrePost=false";
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

  const meta = result.meta || {};
  const closes = (((result.indicators || {}).quote || [{}])[0].close || [])
    .filter((value) => value !== null && value !== undefined)
    .map(Number);
  if (closes.length < 2) throw new Error("日足終値不足");

  const price = Number(meta.regularMarketPrice || closes[closes.length - 1]);
  const previousClose = Number(closes[closes.length - 2]);
  if (!price || !previousClose) throw new Error("日足価格取得失敗");
  const quoteTime = meta.regularMarketTime
    ? new Date(Number(meta.regularMarketTime) * 1000).toISOString()
    : new Date().toISOString();
  return quoteResult(price, previousClose, null, meta.currency || "JPY", quoteTime, meta.marketState || "");
}

function quoteResult(price, previousClose, suppliedChangePercent, currency, quoteTime, marketState) {
  price = Number(price);
  previousClose = Number(previousClose);
  if (!Number.isFinite(price) || !Number.isFinite(previousClose) || previousClose <= 0) {
    throw new Error("価格または前日終値が不正");
  }
  const change = price - previousClose;
  const changePercent = suppliedChangePercent === null || suppliedChangePercent === undefined
    ? change / previousClose * 100
    : suppliedChangePercent;
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
      if (match) return todayJapanTimeIso(Number(match[1]), Number(match[2]));
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
  const date = [
    japan.getUTCFullYear(),
    String(japan.getUTCMonth() + 1).padStart(2, "0"),
    String(japan.getUTCDate()).padStart(2, "0"),
  ].join("-");
  let quoteTime = new Date(date + "T" + String(hour).padStart(2, "0") + ":" + String(minute).padStart(2, "0") + ":00+09:00");
  if (quoteTime.getTime() > now.getTime() + 10 * 60 * 1000) {
    quoteTime = new Date(quoteTime.getTime() - 24 * 60 * 60 * 1000);
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
  if (quoteTime.getTime() > now.getTime() + 10 * 60 * 1000) {
    year -= 1;
    quoteTime = new Date(
      year + "-"
      + String(month).padStart(2, "0") + "-"
      + String(day).padStart(2, "0") + "T"
      + String(hour).padStart(2, "0") + ":"
      + String(minute).padStart(2, "0") + ":00+09:00"
    );
  }
  return quoteTime.toISOString();
}
