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

from app import evaluate_quote, fetch_quote, load_config
from portfolio_master import load_master_payload


BUILD_DIR = ROOT / "build" / "cloud"
PLAIN_DATA_PATH = BUILD_DIR / "plain-data.json"


def quote_payload(item: dict, config: dict) -> dict:
    try:
        quote = fetch_quote(item["symbol"], item.get("name"))
        alert = evaluate_quote(quote, item, config)
        sign = "+" if quote.change_percent >= 0 else ""
        return {
            "symbol": quote.symbol,
            "name": quote.name,
            "price": quote.price,
            "previous_close": quote.previous_close,
            "change": quote.price - quote.previous_close,
            "change_text": f"{sign}{quote.price - quote.previous_close:,.2f}",
            "rate": f"{sign}{quote.change_percent:.2f}%",
            "change_percent": quote.change_percent,
            "currency": quote.currency,
            "alert_direction": alert.direction if alert else None,
            "error": "",
        }
    except Exception as exc:
        return {
            "symbol": item["symbol"],
            "name": item.get("name", ""),
            "error": str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub Pages用の株価データを作ります。")
    parser.add_argument("--skip-fetch", action="store_true", help="株価を取得せず、銘柄マスターだけで作ります。")
    args = parser.parse_args()

    config = load_config(ROOT / "config.json")
    _, portfolios = load_master_payload(config, ROOT)
    unique_symbols = config["symbols"]
    delay = float(config.get("quote_delay_seconds", 1.0))
    quote_by_symbol: dict[str, dict] = {}

    if not args.skip_fetch:
        for index, item in enumerate(unique_symbols):
            quote_by_symbol[item["symbol"]] = quote_payload(item, config)
            if delay > 0 and index < len(unique_symbols) - 1:
                time.sleep(delay)

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
                    "alert_direction": quote.get("alert_direction"),
                    "error": quote.get("error", ""),
                }
            )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "default_up_threshold_percent": config.get("default_up_threshold_percent", 5.0),
        "default_down_threshold_percent": config.get("default_down_threshold_percent", -5.0),
        "symbol_count": len(unique_symbols),
        "portfolios": portfolios.get("portfolios", []),
    }
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    PLAIN_DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(PLAIN_DATA_PATH)


if __name__ == "__main__":
    main()
