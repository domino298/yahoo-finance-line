#!/usr/bin/env python3
import argparse
import html.parser
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from portfolio_master import load_master_payload


YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


@dataclass(frozen=True)
class Quote:
    symbol: str
    name: str
    price: float
    previous_close: float
    change_percent: float
    currency: str
    market_time: Optional[int]


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
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 Chrome Safari",
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
    return float(str(text).replace(",", "").replace("+", "").replace("−", "-").strip())


def fetch_quote_from_yahoo_japan(symbol: str, name: Optional[str] = None) -> Quote:
    url = f"https://finance.yahoo.co.jp/quote/{urllib.parse.quote(symbol)}"
    parser = TextExtractor()
    parser.feed(request_text(url))
    lines = [line.strip() for line in parser.parts if line.strip()]

    try:
        change_index = lines.index("前日比")
    except ValueError as exc:
        raise RuntimeError(f"Missing Yahoo Japan price data for {symbol}") from exc

    price = None
    for line in reversed(lines[:change_index]):
        if re.fullmatch(r"[0-9][0-9,]*(?:\.[0-9]+)?", line):
            price = parse_number(line)
            break

    change_text = lines[change_index + 1] if change_index + 1 < len(lines) else ""
    match = re.search(r"([+\\-−]?[0-9,]+(?:\\.[0-9]+)?)\\s*\\(([+\\-−]?[0-9.]+)%\\)", change_text)
    if price is None or not match:
        raise RuntimeError(f"Missing Yahoo Japan price data for {symbol}")

    change = parse_number(match.group(1))
    change_percent = parse_number(match.group(2))
    previous_close = price - change
    return Quote(
        symbol=symbol,
        name=name or symbol,
        price=price,
        previous_close=previous_close,
        change_percent=change_percent,
        currency="JPY",
        market_time=None,
    )


def fetch_quote(symbol: str, name: Optional[str] = None) -> Quote:
    params = urllib.parse.urlencode({"range": "5d", "interval": "1d"})
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
    if previous_close in (None, 0) and len(closes) >= 2:
        previous_close = closes[-2]

    if price is None or previous_close in (None, 0):
        if symbol.endswith(".T"):
            return fetch_quote_from_yahoo_japan(symbol, name)
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


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} がありません。config.example.json をコピーして作成してください。")
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
        raise ValueError("config.json の symbols に監視銘柄を1つ以上入れてください。")
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
        return "不明"
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def format_alert(alert: Alert) -> str:
    direction_label = "値上がり" if alert.direction == "up" else "値下がり"
    sign = "+" if alert.change_percent >= 0 else ""
    return "\n".join(
        [
            f"{direction_label}通知: {alert.name} ({alert.symbol})",
            f"変化率: {sign}{alert.change_percent:.2f}% / しきい値: {alert.threshold_percent:.2f}%",
            f"現在値: {alert.price:,.2f} {alert.currency}".rstrip(),
            f"前日終値: {alert.previous_close:,.2f} {alert.currency}".rstrip(),
            f"取得時刻: {format_market_time(alert.market_time)}",
        ]
    )


def send_line_message(text: str) -> None:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    to_user_id = os.environ.get("LINE_TO_USER_ID")
    if not token or not to_user_id:
        raise RuntimeError(".env に LINE_CHANNEL_ACCESS_TOKEN と LINE_TO_USER_ID を設定してください。")

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

                mark_sent(alert, state, now)
                sent_count += 1
        if quote_delay_seconds > 0 and index < len(config["symbols"]) - 1:
            time.sleep(quote_delay_seconds)

    save_state(state_path, state)
    return sent_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Yahoo Financeの変化率を監視してLINEに通知します。")
    parser.add_argument("--config", default="config.json", help="設定ファイルのパス")
    parser.add_argument("--once", action="store_true", help="1回だけチェックして終了")
    parser.add_argument("--dry-run", action="store_true", help="LINEに送らず通知内容だけ表示")
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
