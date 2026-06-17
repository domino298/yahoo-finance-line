const MAX_SYMBOLS = 400;

function doGet(e) {
  const params = e && e.parameter ? e.parameter : {};
  const callback = String(params.callback || "");
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

function fetchQuotes(symbols) {
  const quotes = {};
  const fallbackSymbols = [];
  const japanSymbols = symbols;
  const otherSymbols = [];

  const japanRequests = japanSymbols.map((symbol) => ({
    url: "https://finance.yahoo.co.jp/quote/" + encodeURIComponent(symbol),
    muteHttpExceptions: true,
    headers: {
      "User-Agent": "Mozilla/5.0",
      "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
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

function fetchQuoteFromYahooJapan(symbol) {
  const url = "https://finance.yahoo.co.jp/quote/" + encodeURIComponent(symbol);
  const response = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: {
      "User-Agent": "Mozilla/5.0",
      "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    },
  });
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300) {
    throw new Error("Yahoo日本版 HTTP " + response.getResponseCode());
  }

  return parseYahooJapanQuote(symbol, response.getContentText("UTF-8"));
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

  let changeMatch = null;
  for (let index = changeIndex + 1; index < Math.min(lines.length, changeIndex + 8); index += 1) {
    changeMatch = lines[index].match(/([+\-\u2212]?[0-9,]+(?:\.[0-9]+)?)\s*\(([+\-\u2212]?[0-9.]+)%\)/);
    if (changeMatch) break;
  }

  if (price === null || !changeMatch) {
    const close = findPreviousCloseFromYahooJapanLines(lines);
    if (close === null) throw new Error("Yahoo日本版 価格取得失敗");
    price = close;
    return quoteResult(price, close, 0, "JPY", yahooJapanQuoteTime(lines), "CLOSED");
  }

  const change = parseNumber(changeMatch[1]);
  const changePercent = parseNumber(changeMatch[2]);
  const previousClose = price - change;
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
  if (price === previousClose) throw new Error("前日比確認不可");
  const quoteTime = meta.regularMarketTime
    ? new Date(Number(meta.regularMarketTime) * 1000).toISOString()
    : new Date().toISOString();
  return quoteResult(price, previousClose, null, meta.currency || "JPY", quoteTime, meta.marketState || "");
}

function quoteResult(price, previousClose, suppliedChangePercent, currency, quoteTime, marketState) {
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
  return Number(String(value || "").replace(/,/g, "").replace(/\+/g, "").replace(/\u2212/g, "-").trim());
}

function findPreviousCloseFromYahooJapanLines(lines) {
  const closeIndex = lines.indexOf("前日終値");
  if (closeIndex < 0) return null;
  for (let index = closeIndex + 1; index < Math.min(lines.length, closeIndex + 10); index += 1) {
    const match = lines[index].match(/([0-9][0-9,]*(?:\.[0-9]+)?)\([0-9]{2}\/[0-9]{2}\)/);
    if (match) return parseNumber(match[1]);
  }
  return null;
}

function yahooJapanQuoteTime(lines) {
  const realtimeIndex = lines.indexOf("リアルタイム株価");
  if (realtimeIndex >= 0) {
    for (let index = realtimeIndex + 1; index < Math.min(lines.length, realtimeIndex + 5); index += 1) {
      const match = lines[index].match(/^([0-2]?[0-9]):([0-5][0-9])$/);
      if (match) return todayJapanTimeIso(Number(match[1]), Number(match[2]));
    }
  }
  return new Date().toISOString();
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
