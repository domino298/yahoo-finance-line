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
  const change = price - previousClose;
  const changePercent = change / previousClose * 100;
  const quoteTime = meta.regularMarketTime
    ? new Date(Number(meta.regularMarketTime) * 1000).toISOString()
    : new Date().toISOString();
  return {
    price: price,
    previous_close: previousClose,
    change: change,
    change_percent: changePercent,
    currency: meta.currency || "",
    quote_time: quoteTime,
    market_state: meta.marketState || "",
  };
}
