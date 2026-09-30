"""
PRE-MARKET NEWS SCAN — runs ~45 min before the open on trading days.

It reads the overnight news (broad market + the stocks the bot is likely to
touch today) and writes  news/YYYY-MM-DD.json  with:
  - a market read: risk_on / neutral / risk_off  (+ why)
  - per-stock verdicts: positive / neutral / negative / avoid  (+ why)

step10_scan_and_trade.py loads that file during the day and uses it to:
  - pause ALL new stock buys on a genuine risk_off day
  - VETO a buy candidate whose news is "avoid" (missed earnings, downgrade,
    guidance cut, litigation, major bad news)
  - EXIT a held stock whose news turns "avoid" even if the chart still says hold

It never picks stocks on its own and never places a trade. The disciplined
momentum/trend strategy still chooses; this only keeps it off landmines.

Honest note: by the time a headline is public the move is mostly priced in.
The real, achievable value here is *not buying* into a fresh disaster — not
catching winners from good news.

Run it:
    ./venv/bin/python news_scan.py            (skips itself if not a pre-market trading day)
    ./venv/bin/python news_scan.py --force     (run regardless of the clock)
Cost: a few cents per run (claude-opus-5). Change MODEL to trim it.
"""

import os
import re
import sys
import json
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
import anthropic
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

import settings
from scanner import analyze_all, rank_buys

MODEL = "claude-opus-5"          # -> "claude-sonnet-5" / "claude-haiku-4-5" to cut cost
PRICE_IN = 5.00 / 1_000_000
PRICE_OUT = 25.00 / 1_000_000

HERE = os.path.dirname(os.path.abspath(__file__))
NEWS_DIR = os.path.join(HERE, "news")
os.makedirs(NEWS_DIR, exist_ok=True)

load_dotenv()
K, S = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
trading = TradingClient(K, S, paper=True)
data = StockHistoricalDataClient(K, S)
news = NewsClient(K, S)
claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

FORCE = "--force" in sys.argv


def is_premarket_trading_day():
    try:
        clock = trading.get_clock()
        return (not clock.is_open) and clock.next_open.date() == datetime.now(timezone.utc).astimezone(
            clock.next_open.tzinfo).date()
    except Exception:
        return False


def headlines_for(symbols=None, hours=20, limit=40):
    try:
        req = NewsRequest(
            symbols=",".join(symbols) if symbols else None,
            start=datetime.now(timezone.utc) - timedelta(hours=hours),
            limit=limit,
        )
        items = news.get_news(req).data.get("news", [])
        out = []
        for n in items:
            syms = getattr(n, "symbols", []) or []
            out.append({
                "t": n.created_at.strftime("%m-%d %H:%M"),
                "headline": n.headline,
                "summary": (n.summary or "")[:220],
                "symbols": syms[:6],
            })
        return out
    except Exception as e:
        return [{"headline": f"(news fetch failed: {e})", "summary": "", "symbols": [], "t": ""}]


SYSTEM = (
    "You are a pre-market desk analyst for an automated momentum/trend trading bot. "
    "You are given overnight news. Return ONLY a JSON object, no prose, no code fence:\n"
    '{\n'
    '  "market": {"read": "risk_on|neutral|risk_off", "reason": "one sentence"},\n'
    '  "stocks": {\n'
    '     "TICKER": {"verdict": "positive|neutral|negative|avoid", "reason": "one short clause"},\n'
    '     ...\n'
    '  }\n'
    '}\n\n'
    "Rules:\n"
    "- market.read is 'risk_off' ONLY for a genuine broad shock (surprise Fed move, a "
    "sharp overnight index selloff, a real geopolitical/credit event). Ordinary mixed "
    "headlines are 'neutral'. Reserve 'risk_on' for a clear broad positive catalyst.\n"
    "- Per stock: 'avoid' = a concrete negative catalyst that should stop a purchase "
    "today (missed earnings / cut guidance / downgrade / SEC or legal action / major "
    "product or safety failure / accounting issue). 'negative' = softer bad news. "
    "'positive' = a concrete tailwind (earnings beat, upgrade, big deal/contract, "
    "approval). 'neutral' = nothing that matters or no news. When unsure, 'neutral'.\n"
    "- Only include a ticker in 'stocks' if there is real news about IT specifically. "
    "Skip tickers with no relevant news.\n"
    "- Every verdict must rest on an actual NEWS EVENT from the headlines. Do NOT "
    "assign 'negative'/'avoid' for technicals, valuation, or 'looks overbought' — "
    "that's not news. If the only item is a stale performance recap or a vague "
    "opinion piece, the verdict is 'neutral'.\n"
    "- EARNINGS BLACKOUT: if the headlines indicate a ticker reports earnings "
    "today, tonight, tomorrow, or otherwise within about the next 2 trading days "
    "(e.g. 'ahead of Q3 earnings', 'reports after the close today', 'earnings on "
    "deck'), set its verdict to 'avoid' with reason 'earnings <when>' — EVEN IF "
    "the coverage sounds positive. This bot trades trend, not earnings; holding "
    "through a binary event is not its edge, so it should exit beforehand and not "
    "open a new position into one. This is the one case where 'avoid' is allowed "
    "without a negative catalyst."
)


def main():
    if not FORCE and not is_premarket_trading_day():
        print("Not a pre-market trading day (or clock unavailable). Skipping. Use --force to override.")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # what the bot might trade today: momentum shortlist (wide) + what we hold
    held = [p.symbol for p in trading.get_all_positions()
            if str(getattr(p, "asset_class", "")).lower().endswith("us_equity")]
    a = analyze_all(data, list(settings.ALLOWED_STOCKS) + held + ["SPY"])
    shortlist = rank_buys(a, exclude=set(held) | {"SPY"})[:20]
    watch = sorted(set(shortlist) | set(held))

    market_news = headlines_for(None, hours=20, limit=45)
    stock_news = {}
    for sym in watch:
        h = headlines_for([sym], hours=28, limit=5)
        h = [x for x in h if x["headline"] and not x["headline"].startswith("(news fetch failed")]
        if h:
            stock_news[sym] = h

    payload = {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "market_headlines": market_news,
        "stock_headlines": stock_news,
        "bot_would_consider_buying": shortlist[:12],
        "bot_currently_holds": held,
    }

    verdicts = {"market": {"read": "neutral", "reason": "default — analysis unavailable"}, "stocks": {}}
    cost = 0.0
    try:
        msg = claude.messages.create(
            model=MODEL, max_tokens=4000, system=SYSTEM,
            messages=[{"role": "user", "content":
                       "Overnight news follows. Return the JSON.\n\n```json\n"
                       + json.dumps(payload, indent=2, default=str) + "\n```"}],
        )
        raw = "".join(b.text for b in msg.content if b.type == "text").strip()
        cost = round(msg.usage.input_tokens * PRICE_IN + msg.usage.output_tokens * PRICE_OUT, 4)
        cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        parsed = json.loads(cleaned)
        if isinstance(parsed.get("market"), dict) and parsed["market"].get("read") in (
                "risk_on", "neutral", "risk_off"):
            verdicts["market"] = parsed["market"]
        if isinstance(parsed.get("stocks"), dict):
            for k, v in parsed["stocks"].items():
                if isinstance(v, dict) and v.get("verdict") in ("positive", "neutral", "negative", "avoid"):
                    verdicts["stocks"][k.upper()] = {"verdict": v["verdict"], "reason": str(v.get("reason", ""))[:200]}
    except Exception as e:
        verdicts["market"]["reason"] = f"analysis failed ({str(e)[:120]}) — treating as neutral"

    result = {
        "as_of": payload["as_of"], "date": today,
        "market": verdicts["market"], "stocks": verdicts["stocks"],
        "watched": watch, "model": MODEL, "cost_usd": cost,
    }
    with open(os.path.join(NEWS_DIR, f"{today}.json"), "w") as fh:
        json.dump(result, fh, indent=2)

    # human-readable copy for the dashboard
    md = [f"# Pre-market news — {payload['as_of']}\n",
          f"**Market:** `{verdicts['market']['read']}` — {verdicts['market']['reason']}\n"]
    avoid = {k: v for k, v in verdicts["stocks"].items() if v["verdict"] in ("avoid", "negative")}
    good = {k: v for k, v in verdicts["stocks"].items() if v["verdict"] == "positive"}
    if avoid:
        md.append("\n**Bad news — vetoed / flagged for exit:**\n")
        md += [f"- `{k}` ({v['verdict']}) — {v['reason']}" for k, v in avoid.items()]
    if good:
        md.append("\n**Positive catalysts:**\n")
        md += [f"- `{k}` — {v['reason']}" for k, v in good.items()]
    if not verdicts["stocks"]:
        md.append("\n_No stock-specific news that matters today._")
    md.append(f"\n\n<sub>{MODEL} · ~${cost} · watched {len(watch)} names</sub>\n")
    with open(os.path.join(NEWS_DIR, f"{today}.md"), "w") as fh:
        fh.write("\n".join(md))

    print(f"market: {verdicts['market']['read']} — {verdicts['market']['reason']}")
    print(f"stock verdicts: {len(verdicts['stocks'])}  "
          f"(avoid/negative: {list(avoid)})")
    print(f"cost ~${cost}   wrote news/{today}.json")


if __name__ == "__main__":
    main()
