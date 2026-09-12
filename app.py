#!/usr/bin/env python3
import argparse
import html.parser
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from portfolio_master import load_master_payload


YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
JAPAN_TIMEZONE = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Quote:
    symbol: str
    name: str
    price: float
    previous_close: float
    change_percent: float
    currency: str
    market_time: Optional[int]
    warning: str = ""

    def __post_init__(self):
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) or value <= 0
               for value in (self.price, self.previous_close)):
            raise RuntimeError("Invalid price or previous close")
        object.__setattr__(self, "change_percent", (self.price - self.previous_close) / self.previous_close * 100)


@dataclass(frozen=True)
class Alert:
    symbol: str
    name: str
    direction: str
    price: float
    previous_close: float
    change_percent: float
    threshold_percent: float
    currency: str
    market_time: Optional[int]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def request_json(url: str, *, headers: Optional[dict[str, str]] = None, data: Optional[bytes] = None) -> dict:
    request_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 Chrome Safari",
        "Accept": "application/json,text/plain,*/*",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc


def request_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc


class TextExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


def parse_number(text: str) -> float:
    return float(
        str(text)
        .replace(",", "")
        .replace("+", "")
        .replace("\u2212", "-")
        .replace("円", "")
        .replace("％", "")
        .replace("%", "")
        .strip()
    )


def is_japan_market_symbol(symbol: str) -> bool:
    return re.search(r"\.(?:T|N|S|F)$", symbol, flags=re.IGNORECASE) is not None


def is_yahoo_japan_quote_symbol(symbol: str) -> bool:
    return is_japan_market_symbol(symbol) or re.fullmatch(r"[0-9A-Z]{8}", symbol, flags=re.IGNORECASE) is not None


def yahoo_japan_market_timestamp(lines: list[str], change_index: int) -> Optional[int]:
    now = datetime.now(JAPAN_TIMEZONE)
    candidates: list[str] = []
    price_label_index = -1
    for label in ("リアルタイム株価", "15分ディレイ株価"):
        try:
            price_label_index = lines.index(label)
            break
        except ValueError:
            continue
    if price_label_index >= 0:
        candidates.extend(lines[price_label_index + 1 : price_label_index + 6])
    candidates.extend(lines[change_index + 1 : change_index + 12])

    for value in candidates:
        time_match = re.fullmatch(r"([0-2]?[0-9]):([0-5][0-9])", value)
        if time_match:
            # A time without a date cannot identify a previous trading day.
            if now.weekday() >= 5 or now.hour < 9:
                continue
            quote_time = now.replace(
                hour=int(time_match.group(1)),
                minute=int(time_match.group(2)),
                second=0,
                microsecond=0,
            )
            if quote_time > now + timedelta(minutes=10):
                continue
            return int(quote_time.timestamp())

        date_match = re.fullmatch(r"([0-1]?[0-9])/([0-3]?[0-9])", value)
        if date_match:
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            year = now.year - int((month, day) > (now.month, now.day))
            quote_time = datetime(year, month, day, 15, 30, tzinfo=JAPAN_TIMEZONE)
            if quote_time > now:
                continue
            return int(quote_time.timestamp())
    return None


def parse_yahoo_japan_quote_html(symbol: str, page_html: str, name: Optional[str] = None) -> Quote:
    parser = TextExtractor()
    parser.feed(page_html)
    lines = [line.strip() for line in parser.parts if line.strip()]

    try:
        change_index = lines.index("\u524d\u65e5\u6bd4")
    except ValueError as exc:
        raise RuntimeError(f"Missing Yahoo Japan price data for {symbol}") from exc

    price = None
    for line in reversed(lines[:change_index]):
        if re.fullmatch(r"[0-9][0-9,]*(?:\.[0-9]+)?", line):
            price = parse_number(line)
            break

    change = None
    change_percent = None
    change_lines = lines[change_index + 1 : change_index + 8]
    joined_change = "".join(change_lines)
    joined_match = re.match(
        r"([+\-\u2212]?[0-9,]+(?:\.[0-9]+)?)\(([+\-\u2212]?[0-9.]+)%\)",
        joined_change,
    )
    if joined_match:
        change = parse_number(joined_match.group(1))
        change_percent = parse_number(joined_match.group(2))

    for line in change_lines:
        if change is not None and change_percent is not None:
            break
        combined_match = re.search(
            r"([+\-\u2212]?[0-9,]+(?:\.[0-9]+)?)\s*\(([+\-\u2212]?[0-9.]+)%\)",
            line,
        )
        if combined_match:
            change = parse_number(combined_match.group(1))
            change_percent = parse_number(combined_match.group(2))
            break
        if change is None and re.fullmatch(r"[+\-\u2212][0-9,]+(?:\.[0-9]+)?", line):
            change = parse_number(line)
        percent_match = re.fullmatch(r"\(([+\-\u2212]?[0-9.]+)%\)", line) or re.fullmatch(
            r"([+\-\u2212]?[0-9.]+)%", line
        )
        if change_percent is None and percent_match:
            change_percent = parse_number(percent_match.group(1))

    if price is None or change is None or change_percent is None:
        raise RuntimeError(f"Missing current Yahoo Japan price data for {symbol}")

    previous_close = price - change
    if previous_close <= 0:
        raise RuntimeError(f"Invalid Yahoo Japan previous close for {symbol}")
    if abs(change / previous_close * 100 - change_percent) > 0.011:
        raise RuntimeError(f"Inconsistent Yahoo Japan price data for {symbol}")

    return Quote(
        symbol=symbol,
        name=name or symbol,
        price=price,
        previous_close=previous_close,
        change_percent=(price - previous_close) / previous_close * 100,
        currency="JPY",
        market_time=yahoo_japan_market_timestamp(lines, change_index),
    )


def fetch_quote_from_yahoo_japan(symbol: str, name: Optional[str] = None) -> Quote:
    url = f"https://finance.yahoo.co.jp/quote/{urllib.parse.quote(symbol)}"
    return parse_yahoo_japan_quote_html(symbol, request_text(url), name)


class HistoryTableParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def parse_yahoo_japan_history_html(symbol: str, page_html: str, name: Optional[str] = None,
                                  now: Optional[datetime] = None) -> Quote:
    parser = HistoryTableParser()
    parser.feed(page_html)
    now = now or datetime.now(JAPAN_TIMEZONE)
    rows: list[tuple[str, float]] = []
    close_index = 4 if is_japan_market_symbol(symbol) else None
    for cells in parser.rows:
        if not cells:
            continue
        if cells[0] == "日付":
            close_index = next((i for i, value in enumerate(cells)
                                if value in ("終値", "基準価額")), None)
            continue
        if not re.fullmatch(r"20[0-9]{2}/[0-1]?[0-9]/[0-3]?[0-9]", cells[0]):
            continue
        session = datetime.strptime(cells[0], "%Y/%m/%d").replace(hour=15, minute=30, tzinfo=JAPAN_TIMEZONE)
        if session > now:
            continue
        if close_index is None or len(cells) <= close_index:
            raise RuntimeError(f"Unknown Yahoo Japan history columns for {symbol}")
        close = parse_number(cells[close_index])
        rows.append((session.date().isoformat(), close))

    rows = sorted(dict(rows).items(), reverse=True)

    if len(rows) < 2:
        raise RuntimeError(f"Missing Yahoo Japan history data for {symbol}")
    current_date, price = rows[0]
    _, previous_close = rows[1]
    market_time = int(datetime.strptime(current_date, "%Y-%m-%d").replace(
        hour=15, minute=30, tzinfo=JAPAN_TIMEZONE
    ).timestamp())
    return Quote(
        symbol=symbol,
        name=name or symbol,
        price=price,
        previous_close=previous_close,
        change_percent=(price - previous_close) / previous_close * 100,
        currency="JPY",
        market_time=market_time,
        warning="履歴終値（現在値の取得失敗時の参考値）",
    )


def fetch_quote_from_yahoo_japan_history(symbol: str, name: Optional[str] = None) -> Quote:
    url = f"https://finance.yahoo.co.jp/quote/{urllib.parse.quote(symbol)}/history"
    return parse_yahoo_japan_history_html(symbol, request_text(url), name)


def session_date_from_timestamp(timestamp: float, utc_offset_seconds: int = 0) -> str:
    adjusted = datetime.fromtimestamp(float(timestamp) + utc_offset_seconds, timezone.utc)
    return adjusted.date().isoformat()


def daily_close_entries(chart_result: dict, symbol: str = "") -> list[tuple[int, float, str]]:
    meta = chart_result.get("meta", {})
    fallback_offset = 9 * 60 * 60 if is_japan_market_symbol(symbol or meta.get("symbol", "")) else 0
    offset = int(meta.get("gmtoffset") or fallback_offset)
    timestamps = chart_result.get("timestamp") or []
    closes = (
        chart_result.get("indicators", {})
        .get("quote", [{}])[0]
        .get("close", [])
        or []
    )
    entries = []
    for timestamp, close in zip(timestamps, closes):
        if close is None:
            continue
        close_value = float(close)
        if not math.isfinite(close_value) or close_value <= 0:
            raise RuntimeError("Invalid daily close")
        close_value = round(close_value, min(8, max(0, int(meta.get("priceHint", 6)))))
        timestamp_value = int(timestamp)
        entries.append((timestamp_value, close_value, session_date_from_timestamp(timestamp_value, offset)))
    return sorted(entries)


def quote_from_daily_chart_result(symbol: str, chart_result: dict, name: Optional[str] = None) -> Quote:
    meta = chart_result.get("meta", {})
    entries = daily_close_entries(chart_result, symbol)
    if len(entries) < 2:
        raise RuntimeError(f"Missing daily close data for {symbol}")

    fallback_offset = 9 * 60 * 60 if is_japan_market_symbol(symbol) else 0
    offset = int(meta.get("gmtoffset") or fallback_offset)
    if not meta.get("regularMarketTime"):
        raise RuntimeError(f"Missing quote timestamp for {symbol}")
    regular_market_time = int(meta["regularMarketTime"])
    quote_session_date = session_date_from_timestamp(regular_market_time, offset)
    market_state = str(meta.get("marketState") or "").upper()

    # Chart responses can omit marketState; regularMarketPrice still carries
    # the last regular-session trade, including outside market hours.
    if market_state not in ("CLOSED", "PRE", "PREPRE", "POST", "POSTPOST"):
        price = meta.get("regularMarketPrice")
        if price is None:
            same_session = [entry for entry in entries if entry[2] == quote_session_date]
            if not same_session:
                raise RuntimeError(f"Missing regular-session price for {symbol}")
            price = same_session[-1][1]
        previous_candidates = [entry for entry in entries if entry[2] < quote_session_date]
        market_time = regular_market_time
    else:
        completed_sessions = [entry for entry in entries if entry[2] == quote_session_date]
        if not completed_sessions:
            raise RuntimeError(f"Missing completed-session close for {symbol}")
        current_session = completed_sessions[-1]
        price = current_session[1]
        regular_price = meta.get("regularMarketPrice")
        if regular_price is not None and abs(float(regular_price) - price) > 0.011:
            raise RuntimeError(f"Conflicting final close and regular price for {symbol}")
        quote_session_date = current_session[2]
        previous_candidates = [entry for entry in entries if entry[2] < quote_session_date]
        market_time = regular_market_time

    if not previous_candidates:
        raise RuntimeError(f"Missing previous-session close for {symbol}")
    previous_close = previous_candidates[-1][1]
    # Do not skip a missing intervening candle and use a two-session-old close.
    raw_previous_dates = [session_date_from_timestamp(ts, offset)
                          for ts in chart_result.get("timestamp", [])
                          if session_date_from_timestamp(ts, offset) < quote_session_date]
    if raw_previous_dates and max(raw_previous_dates) != previous_candidates[-1][2]:
        raise RuntimeError(f"Missing immediately previous-session close for {symbol}")
    price = round(float(price), min(8, max(0, int(meta.get("priceHint", 6)))))
    change_percent = (price - previous_close) / previous_close * 100
    return Quote(
        symbol=symbol,
        name=name or meta.get("shortName") or symbol,
        price=price,
        previous_close=previous_close,
        change_percent=change_percent,
        currency=meta.get("currency") or "",
        market_time=market_time,
    )


def fetch_quote_from_chart(symbol: str, name: Optional[str] = None) -> Quote:
    is_japan_stock = is_japan_market_symbol(symbol)
    if is_japan_stock:
        daily_params = urllib.parse.urlencode({"range": "1mo", "interval": "1d", "includePrePost": "false"})
        daily_url = f"{YAHOO_CHART_URL.format(symbol=urllib.parse.quote(symbol))}?{daily_params}"
        daily_payload = request_json(daily_url)
        daily_result = daily_payload.get("chart", {}).get("result") or []
        if not daily_result:
            raise RuntimeError(f"Missing daily previous close data for {symbol}")
        return quote_from_daily_chart_result(symbol, daily_result[0], name)

    params = urllib.parse.urlencode({"range": "1d", "interval": "1m", "includePrePost": "false"})
    url = f"{YAHOO_CHART_URL.format(symbol=urllib.parse.quote(symbol))}?{params}"
    payload = request_json(url)

    result = payload.get("chart", {}).get("result") or []
    if not result:
        error = payload.get("chart", {}).get("error")
        raise RuntimeError(f"No quote data for {symbol}: {error}")

    item = result[0]
    meta = item.get("meta", {})
    price = meta.get("regularMarketPrice")
    previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")

    closes = [
        value
        for value in (
            item.get("indicators", {})
            .get("quote", [{}])[0]
            .get("close", [])
            or []
        )
        if value is not None
    ]
    if price is None and closes:
        price = closes[-1]

    if price is None or previous_close in (None, 0):
        raise RuntimeError(f"Missing price data for {symbol}")

    change_percent = (float(price) - float(previous_close)) / float(previous_close) * 100
    return Quote(
        symbol=symbol,
        name=name or meta.get("shortName") or symbol,
        price=float(price),
        previous_close=float(previous_close),
        change_percent=change_percent,
        currency=meta.get("currency") or "",
        market_time=meta.get("regularMarketTime"),
    )


def fetch_quote(symbol: str, name: Optional[str] = None) -> Quote:
    if is_japan_market_symbol(symbol):
        try:
            return fetch_quote_from_chart(symbol, name)
        except Exception:
            try:
                quote = fetch_quote_from_yahoo_japan(symbol, name)
                if quote.market_time is None:
                    raise RuntimeError("Yahoo Japan quote date is unknown")
                return quote
            except Exception:
                return fetch_quote_from_yahoo_japan_history(symbol, name)
    if is_yahoo_japan_quote_symbol(symbol):
        try:
            return fetch_quote_from_yahoo_japan(symbol, name)
        except Exception:
            return fetch_quote_from_yahoo_japan_history(symbol, name)
    return fetch_quote_from_chart(symbol, name)


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist. Copy config.example.json to create it.")
    with path.open(encoding="utf-8") as file:
        config = json.load(file)

    if config.get("symbol_source") == "excel":
        symbols, _ = load_master_payload(config, path.parent)
        thresholds_by_symbol = {item.get("symbol"): item for item in config.get("symbols", [])}
        merged_symbols = []
        for item in symbols:
            existing = thresholds_by_symbol.get(item["symbol"], {})
            merged = {**item}
            for key in ("up_threshold_percent", "down_threshold_percent"):
                if key in existing:
                    merged[key] = existing[key]
            merged_symbols.append(merged)
        config["symbols"] = merged_symbols

    if not config.get("symbols"):
        raise ValueError("Add at least one monitored symbol to symbols in config.json.")
    return config


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"sent": {}}
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def should_send(alert: Alert, state: dict, cooldown_hours: float, now: float) -> bool:
    key = f"{alert.symbol}:{alert.direction}"
    last_sent = state.get("sent", {}).get(key)
    if last_sent is None:
        return True
    return now - float(last_sent) >= cooldown_hours * 60 * 60


def mark_sent(alert: Alert, state: dict, now: float) -> None:
    state.setdefault("sent", {})[f"{alert.symbol}:{alert.direction}"] = now


def evaluate_quote(quote: Quote, symbol_config: dict, config: dict) -> Optional[Alert]:
    if quote.warning:
        return None
    up_threshold = float(symbol_config.get("up_threshold_percent", config["default_up_threshold_percent"]))
    down_threshold = float(symbol_config.get("down_threshold_percent", config["default_down_threshold_percent"]))

    if quote.change_percent >= up_threshold:
        return Alert(
            symbol=quote.symbol,
            name=quote.name,
            direction="up",
            price=quote.price,
            previous_close=quote.previous_close,
            change_percent=quote.change_percent,
            threshold_percent=up_threshold,
            currency=quote.currency,
            market_time=quote.market_time,
        )
    if quote.change_percent <= down_threshold:
        return Alert(
            symbol=quote.symbol,
            name=quote.name,
            direction="down",
            price=quote.price,
            previous_close=quote.previous_close,
            change_percent=quote.change_percent,
            threshold_percent=down_threshold,
            currency=quote.currency,
            market_time=quote.market_time,
        )
    return None


def format_market_time(timestamp: Optional[int]) -> str:
    if timestamp is None:
        return "unknown"
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def format_alert(alert: Alert) -> str:
    direction_label = "値上がり通知" if alert.direction == "up" else "値下がり通知"
    sign = "+" if alert.change_percent >= 0 else ""
    return "\n".join(
        [
            f"{direction_label}: {alert.name} ({alert.symbol})",
            f"騰落率: {sign}{alert.change_percent:.2f}% / 基準: {alert.threshold_percent:.2f}%",
            f"現在値: {alert.price:,.2f} {alert.currency}".rstrip(),
            f"前日終値: {alert.previous_close:,.2f} {alert.currency}".rstrip(),
            f"株価時点: {format_market_time(alert.market_time)}",
        ]
    )


def send_line_message(text: str) -> None:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    to_user_id = os.environ.get("LINE_TO_USER_ID")
    if not token or not to_user_id:
        raise RuntimeError("Set LINE_CHANNEL_ACCESS_TOKEN and LINE_TO_USER_ID in .env.")

    body = json.dumps(
        {
            "to": to_user_id,
            "messages": [{"type": "text", "text": text[:5000]}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request_json(
        LINE_PUSH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        data=body,
    )


def run_once(config_path: Path, dry_run: bool = False) -> int:
    config = load_config(config_path)
    state_path = Path(config.get("state_file", "state.json"))
    if not state_path.is_absolute():
        state_path = config_path.parent / state_path

    state = load_state(state_path)
    cooldown_hours = float(config.get("cooldown_hours", 24))
    quote_delay_seconds = float(config.get("quote_delay_seconds", 0.3))
    now = time.time()
    sent_count = 0

    for index, symbol_config in enumerate(config["symbols"]):
        symbol = symbol_config["symbol"]
        try:
            quote = fetch_quote(symbol, symbol_config.get("name"))
            alert = evaluate_quote(quote, symbol_config, config)
        except Exception as exc:
            print(f"[ERROR] {symbol}: {exc}", file=sys.stderr)
        else:
            if alert is None:
                print(f"[OK] {quote.name} ({quote.symbol}) {quote.change_percent:+.2f}%")
            elif not should_send(alert, state, cooldown_hours, now):
                print(f"[SKIP] {alert.name} ({alert.symbol}) {alert.change_percent:+.2f}% cooldown")
            else:
                message = format_alert(alert)
                if dry_run:
                    print("[DRY-RUN]")
                    print(message)
                else:
                    send_line_message(message)
                    print(f"[SENT] {alert.name} ({alert.symbol}) {alert.change_percent:+.2f}%")

                if not dry_run:
                    mark_sent(alert, state, now)
                    save_state(state_path, state)
                sent_count += 1
        if quote_delay_seconds > 0 and index < len(config["symbols"]) - 1:
            time.sleep(quote_delay_seconds)

    if not dry_run:
        save_state(state_path, state)
    return sent_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor Yahoo Finance change rates and send LINE alerts.")
    parser.add_argument("--config", default="config.json", help="Config file path")
    parser.add_argument("--once", action="store_true", help="Check once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print alerts without sending them to LINE")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    load_dotenv(config_path.parent / ".env")

    if args.once:
        run_once(config_path, dry_run=args.dry_run)
        return 0

    while True:
        config = load_config(config_path)
        interval = int(config.get("check_interval_seconds", 900))
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[START] {started_at}")
        run_once(config_path, dry_run=args.dry_run)
        print(f"[SLEEP] {interval} seconds")
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
