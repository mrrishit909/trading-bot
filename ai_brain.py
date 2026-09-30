"""
STEP 9: The AI brain.

Same job as robot.py (look at a stock, say BUY / SELL / WAIT), but instead of
just comparing two averages, this:
  - gathers recent prices, the average-crossover signal, recent % moves,
    and the latest news headlines
  - hands all of that to Claude and asks for a decision + a short reason
  - returns it in the SAME shape as robot.py so the rest of our code
    (the bouncer, the diary) doesn't need to change

IMPORTANT: this is a learning toy on PRETEND money. It is not financial advice.
The AI still has to get past the same safety bouncer as the dumb robot.
"""

import os
import json
from datetime import datetime, timezone, timedelta

from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest, NewsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment

STRATEGY_NAME = "claude_advisor_v1"
MODEL = "claude-haiku-4-5-20251001"

FAST_DAYS = 5
SLOW_DAYS = 20

# Rough Haiku pricing (USD per million tokens). Just for a cost estimate in the diary.
PRICE_IN = 1.00 / 1_000_000
PRICE_OUT = 5.00 / 1_000_000


def _avg(xs):
    return sum(xs) / len(xs)


def _gather(data_client, news_client, symbol):
    """Collect everything we want the AI to look at."""
    start = datetime.now(timezone.utc) - timedelta(days=45)
    bars = data_client.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start,
        adjustment=Adjustment.ALL,
    )).data.get(symbol, [])
    closes = [b.close for b in bars]

    quote = data_client.get_stock_latest_quote(
        StockLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
    price_now = quote.ask_price or quote.bid_price

    headlines = []
    try:
        news = news_client.get_news(NewsRequest(
            symbols=symbol,
            start=datetime.now(timezone.utc) - timedelta(days=5),
            limit=6,
        )).data.get("news", [])
        headlines = [f"{n.created_at.date()}: {n.headline}" for n in news]
    except Exception:
        pass

    info = {
        "symbol": symbol,
        "price_now": round(price_now, 2) if price_now else None,
        "closes_last_10": [round(c, 2) for c in closes[-10:]],
        "bars_available": len(closes),
    }
    if len(closes) >= SLOW_DAYS:
        fast = _avg(closes[-FAST_DAYS:])
        slow = _avg(closes[-SLOW_DAYS:])
        info["fast_avg_5d"] = round(fast, 2)
        info["slow_avg_20d"] = round(slow, 2)
        info["crossover_signal"] = "UP (fast above slow)" if fast > slow else "DOWN (fast below slow)"
        info["change_1d_pct"] = round((closes[-1] / closes[-2] - 1) * 100, 2)
        info["change_5d_pct"] = round((closes[-1] / closes[-6] - 1) * 100, 2)
    info["recent_headlines"] = headlines
    return info, (info.get("fast_avg_5d"), info.get("slow_avg_20d"))


SYSTEM = (
    "You are a cautious trading assistant for a PAPER-MONEY (pretend) learning project. "
    "You are given data about one stock and must choose ONE action: BUY, SELL, or WAIT. "
    "BUY means open/add a small position. SELL means close what we hold. WAIT means do nothing. "
    "Be conservative: prefer WAIT unless the picture is reasonably clear. "
    "This is not financial advice; it is a coding exercise. "
    'Reply with ONLY a JSON object: {"action": "BUY|SELL|WAIT", "confidence": 0.0-1.0, '
    '"reason": "one or two plain sentences"}'
)


def advise(data_client, news_client, anthropic_client, symbol, do_we_own_it):
    symbol = symbol.upper()
    info, (fast, slow) = _gather(data_client, news_client, symbol)

    user_msg = (
        f"We currently {'OWN' if do_we_own_it else 'do NOT own'} {symbol}.\n\n"
        f"Data:\n{json.dumps(info, indent=2)}\n\n"
        "Give your JSON decision."
    )

    context = {"strategy": STRATEGY_NAME, "model": MODEL, "sent_to_ai": info,
               "owned_before": do_we_own_it}

    try:
        msg = anthropic_client.messages.create(
            model=MODEL, max_tokens=400, system=SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = msg.content[0].text.strip()
        context["ai_raw_reply"] = raw
        context["tokens_in"] = msg.usage.input_tokens
        context["tokens_out"] = msg.usage.output_tokens
        context["cost_usd_est"] = round(
            msg.usage.input_tokens * PRICE_IN + msg.usage.output_tokens * PRICE_OUT, 5)

        # pull the JSON out even if wrapped in ```json fences
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(cleaned)
        action = parsed.get("action", "WAIT").upper()
        if action not in ("BUY", "SELL", "WAIT"):
            action = "WAIT"
        confidence = parsed.get("confidence")
        reason = parsed.get("reason", "(no reason given)")
        context["ai_confidence"] = confidence
    except Exception as e:
        action = "WAIT"
        reason = f"AI brain had a problem, so playing safe with WAIT. ({e})"
        context["error"] = str(e)

    # sanity: don't SELL what we don't own, don't BUY what we already hold
    if action == "SELL" and not do_we_own_it:
        action, reason = "WAIT", f"AI said SELL but we own none. WAIT. (was: {reason})"
    if action == "BUY" and do_we_own_it:
        action, reason = "WAIT", f"AI said BUY but we already hold it. WAIT. (was: {reason})"

    return {"action": action, "reason": reason, "fast": fast, "slow": slow, "context": context}
