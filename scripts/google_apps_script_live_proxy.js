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

  for (const symbol of symbols) {
    try {
      payload.quotes[symbol] = fetchQuote(symbol);
      if (
        payload.quotes[symbol].quote_time
        && (!payload.quote_time || new Date(payload.quotes[symbol].quote_time) > new Date(payload.quote_time))
      ) {
        payload.quote_time = payload.quotes[symbol].quote_time;
      }
      payload.success += 1;
    } catch (error) {
      payload.quotes[symbol] = { error: String(error).replace(/^Error: /, "") };
    }
  }
  if (!payload.quote_time) payload.quote_time = payload.generated_at;

  const json = JSON.stringify(payload);
  if (/^[A-Za-z_$][0-9A-Za-z_$]*(\.[A-Za-z_$][0-9A-Za-z_$]*)*$/.test(callback)) {
    const statusScript = [
      "setTimeout(function(){",
      "try{",
      "var el=document.getElementById('statusText');",
      "if(el){",
      "var q=new Date(" + JSON.stringify(payload.quote_time) + ");",
      "var g=new Date(" + JSON.stringify(payload.generated_at) + ");",
      "el.textContent='株価時点: '+q.toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'})+' / 取得: '+g.toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'});",
      "}",
      "}catch(e){}",
      "},300);",
    ].join("");
    return ContentService
      .createTextOutput(callback + "(" + json + ");" + statusScript)
      .setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return ContentService
    .createTextOutput(json)
    .setMimeType(ContentService.MimeType.JSON);
}

function fetchQuote(symbol) {
  if (/\.T$/.test(symbol)) {
    try {
      return fetchQuoteFromYahooJapan(symbol);
    } catch (error) {
      // Yahoo!ファイナンス日本版を優先し、取れない時だけチャートAPIに戻します。
    }
  }
  return fetchQuoteFromChart(symbol);
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

  const lines = htmlToLines(response.getContentText("UTF-8"));
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
  return new Date(date + "T" + String(hour).padStart(2, "0") + ":" + String(minute).padStart(2, "0") + ":00+09:00").toISOString();
}
