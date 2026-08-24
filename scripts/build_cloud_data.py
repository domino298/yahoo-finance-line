#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import evaluate_quote, fetch_quote, fetch_quote_from_chart, is_yahoo_japan_quote_symbol, load_config
from portfolio_master import load_master_payload


BUILD_DIR = ROOT / "build" / "cloud"
PLAIN_DATA_PATH = BUILD_DIR / "plain-data.json"


def quote_payload(item: dict, config: dict) -> dict:
    try:
        symbol = item["symbol"]
        if symbol.upper().endswith(".T") or not is_yahoo_japan_quote_symbol(symbol):
            quote = fetch_quote_from_chart(symbol, item.get("name"))
        else:
            quote = fetch_quote(symbol, item.get("name"))
        alert = evaluate_quote(quote, item, config)
        change = quote.price - quote.previous_close
        sign = "+" if change >= 0 else ""
        return {
            "symbol": quote.symbol,
            "name": quote.name,
            "price": quote.price,
            "previous_close": quote.previous_close,
            "change": change,
            "change_text": f"{sign}{change:,.2f}",
            "rate": f"{sign}{quote.change_percent:.2f}%",
            "change_percent": quote.change_percent,
            "currency": quote.currency,
            "quote_time": datetime.fromtimestamp(quote.market_time, timezone.utc).isoformat() if quote.market_time else "",
            "alert_direction": alert.direction if alert else None,
            "error": "",
        }
    except Exception as exc:
        return {
            "symbol": item["symbol"],
            "name": item.get("name", ""),
            "error": str(exc),
        }


def fetch_quote_payloads(unique_symbols: list[dict], config: dict) -> dict[str, dict]:
    delay = max(0.0, float(config.get("quote_delay_seconds", 1.0)))
    retry_attempts = max(0, int(config.get("quote_retry_attempts", 2)))
    retry_pause = max(0.0, float(config.get("quote_retry_pause_seconds", 5.0)))
    retry_delay = max(0.0, float(config.get("quote_retry_delay_seconds", 1.0)))
    quote_by_symbol: dict[str, dict] = {}
    fetch_order = sorted(
        unique_symbols,
        key=lambda item: 0
        if is_yahoo_japan_quote_symbol(item["symbol"]) and not item["symbol"].upper().endswith(".T")
        else 1,
    )

    for index, item in enumerate(fetch_order):
        quote_by_symbol[item["symbol"]] = quote_payload(item, config)
        if delay > 0 and index < len(fetch_order) - 1:
            time.sleep(delay)
    for _ in range(retry_attempts):
        failed_items = [item for item in unique_symbols if quote_by_symbol[item["symbol"]].get("error")]
        if not failed_items:
            break
        if retry_pause > 0:
            time.sleep(retry_pause)
        for index, item in enumerate(failed_items):
            quote_by_symbol[item["symbol"]] = quote_payload(item, config)
            if retry_delay > 0 and index < len(failed_items) - 1:
                time.sleep(retry_delay)
    return quote_by_symbol


def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub Pages用の株価データを作ります。")
    parser.add_argument("--skip-fetch", action="store_true", help="株価を取得せず、銘柄マスターだけで作ります。")
    args = parser.parse_args()

    config = load_config(ROOT / "config.json")
    _, portfolios = load_master_payload(config, ROOT)
    unique_symbols = config["symbols"]
    quote_by_symbol: dict[str, dict] = {}

    if not args.skip_fetch:
        quote_by_symbol = fetch_quote_payloads(unique_symbols, config)
    quote_times = [
        quote.get("quote_time")
        for quote in quote_by_symbol.values()
        if quote.get("quote_time")
    ]
    japan_quote_times = [
        quote.get("quote_time")
        for symbol, quote in quote_by_symbol.items()
        if is_yahoo_japan_quote_symbol(symbol) and quote.get("quote_time")
    ]
    generated_at = datetime.now(timezone.utc).isoformat()

    for portfolio in portfolios.get("portfolios", []):
        for item in portfolio.get("symbols", []):
            quote = quote_by_symbol.get(item["symbol"], {})
            item.update(
                {
                    "price": quote.get("price", ""),
                    "previous_close": quote.get("previous_close", ""),
                    "change": quote.get("change_text", ""),
                    "rate": quote.get("rate", ""),
                    "change_percent": quote.get("change_percent"),
                    "currency": quote.get("currency", ""),
                    "quote_time": quote.get("quote_time", ""),
                    "alert_direction": quote.get("alert_direction"),
                    "error": quote.get("error", ""),
                }
            )

    payload = {
        "generated_at": generated_at,
        "quote_time": max(japan_quote_times or quote_times) if (japan_quote_times or quote_times) else generated_at,
        "default_up_threshold_percent": config.get("default_up_threshold_percent", 5.0),
        "default_down_threshold_percent": config.get("default_down_threshold_percent", -5.0),
        "symbol_count": len(unique_symbols),
        "portfolios": portfolios.get("portfolios", []),
    }
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    PLAIN_DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    success_count = sum(not item.get("error") for item in quote_by_symbol.values())
    failed_count = len(quote_by_symbol) - success_count
    print(f"quotes: OK {success_count} / failed {failed_count} / total {len(quote_by_symbol)}")
    print(PLAIN_DATA_PATH)


if __name__ == "__main__":
    main()
