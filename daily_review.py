"""
DAILY REVIEW — the bot's "research and learn" routine.

Once a day it pulls together everything about how the account is doing —
completed trades vs the S&P, what's winning and losing, the current market,
news on what we hold, the strategy settings, and its own notes from the last
few days — and asks Claude for an honest written analysis:
  * what's actually working / not working (with sample-size caveats)
  * patterns in the wins vs the losses
  * what the market is doing and how we're positioned
  * 1-3 hypotheses worth watching (ideas, NOT orders)

It writes a dated note to  research/YYYY-MM-DD.md  and prepends a short
summary to  research/LESSONS.md  (a running journal). It NEVER changes any
setting or places any trade — a human reads the notes and decides.

Run it:
    ./venv/bin/python daily_review.py
    ./venv/bin/python daily_review.py --profile sprint500
Cost: a few cents per run (claude-opus-5). Change MODEL below to trim it.
"""

import os
import re
import sys
import json
import glob
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
import anthropic
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

import profiles

# ---- pick the account profile (same mechanism as auto_run / dashboard) -----
HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE_NAME = "main"
if "--profile" in sys.argv:
    PROFILE_NAME = sys.argv[sys.argv.index("--profile") + 1]
PROFILE = profiles.get(PROFILE_NAME)
load_dotenv(os.path.join(HERE, PROFILE["env_file"]), override=True)
os.environ.setdefault("ROBOT_DIARY_PATH", os.path.join(HERE, PROFILE["diary"]))
os.environ["ROBOT_PROFILE"] = PROFILE_NAME

import settings          # noqa: E402  (must come after env is set)
import diary             # noqa: E402
from grader import grade_trades, grade_all          # noqa: E402
from scanner import analyze_all, rank_buys          # noqa: E402

MODEL = "claude-opus-5"          # -> "claude-sonnet-5" or "claude-haiku-4-5" to cut cost
PRICE_IN = 5.00 / 1_000_000      # rough claude-opus-5 rates, for the cost line
PRICE_OUT = 25.00 / 1_000_000

RESEARCH_DIR = os.path.join(HERE, "research")
os.makedirs(RESEARCH_DIR, exist_ok=True)

K, S = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
trading = TradingClient(K, S, paper=True)
data = StockHistoricalDataClient(K, S)
cdc = CryptoHistoricalDataClient()
news = NewsClient(K, S)
claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
db = diary.get_db()


def _money(x):
    try:
        return f"${float(x):,.2f}"
    except (TypeError, ValueError):
        return "-"


def gather():
    """Everything the analyst gets to look at, as a plain dict."""
    acct = trading.get_account()
    equity, cash = float(acct.equity), float(acct.cash)
    day_change = equity - float(acct.last_equity)

    first = db.execute("SELECT equity_before FROM runs WHERE equity_before IS NOT NULL "
                       "ORDER BY run_id LIMIT 1").fetchone()
    start_equity = float(first["equity_before"]) if first else None

    positions = []
    held_stocks, held_crypto = [], []
    for p in trading.get_all_positions():
        klass = str(getattr(p, "asset_class", "")).lower()
        row = {
            "symbol": p.symbol, "qty": round(float(p.qty), 6),
            "value": round(float(p.market_value), 2),
            "pnl": round(float(p.unrealized_pl), 2),
            "pnl_pct": round(float(p.unrealized_plpc) * 100, 1),
            "kind": "crypto" if klass.endswith("crypto") else
                    "option" if klass.endswith("us_option") else "stock",
        }
        positions.append(row)
        if row["kind"] == "stock":
            held_stocks.append(p.symbol)
        elif row["kind"] == "crypto":
            held_crypto.append(p.symbol)

    # completed round trips vs SPY, and signal accuracy
    try:
        trades = grade_trades(data, db)
    except Exception as e:
        trades = {"_error": str(e)[:200]}
    try:
        signal = grade_all(data, db, lookahead=10)
    except Exception as e:
        signal = {"_error": str(e)[:200]}
    if isinstance(signal, dict) and "_error" not in signal:
        # make the deliberate omissions explicit so they don't read as a broken pipeline
        signal.setdefault("crypto_sma_v1", {
            "graded_elsewhere": "realised round-trip P/L in completed_trades_vs_spy.crypto_sma_v1 "
            "— forward-price signal accuracy is not computed for crypto, by design"})
        signal.setdefault("options_long_v1", {
            "graded_elsewhere": "options trading is OFF; see completed_trades_vs_spy.options_long_v1 "
            "for the closed history"})

    # decisions in the last 7 days, by strategy + action — LIVE runs only.
    # (--pretend test runs also write decisions; counting them makes it look
    # like the bot decided to sell 10 times and only filled once.)
    dec_counts = db.execute("""
        SELECT r.strategy, d.action, COUNT(*) n
        FROM decisions d JOIN runs r ON d.run_id = r.run_id
        WHERE d.ts_utc >= ? AND r.mode != 'pretend'
        GROUP BY r.strategy, d.action ORDER BY 1, 2
    """, ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),)).fetchall()
    decisions_7d = [dict(r) for r in dec_counts]

    # filled trades, last 14 days (live only)
    tr = db.execute("""
        SELECT substr(t.ts_utc,1,16) ts, r.strategy, t.symbol, t.side, t.shares,
               t.fill_price, t.note
        FROM trades t JOIN runs r ON t.run_id = r.run_id
        WHERE t.status = 'filled' AND r.mode != 'pretend' AND t.ts_utc >= ?
        ORDER BY t.trade_id DESC LIMIT 40
    """, ((datetime.now(timezone.utc) - timedelta(days=14)).isoformat(),)).fetchall()
    trades_14d = [dict(r) for r in tr]

    # the current strategy knobs
    knobs = {k: getattr(settings, k) for k in [
        "MAX_STOCKS_HELD", "DOLLARS_PER_BUY", "STOCK_STOP_LOSS_PCT", "TRAILING_STOP_PCT",
        "SHORTLIST_SIZE", "USE_MARKET_FILTER", "REBUY_COOLDOWN_DAYS", "USE_MOMENTUM_RANK",
        "REQUIRE_POSITIVE_QUARTER", "RSI_OVERBOUGHT", "USE_ATR_STOP", "USE_VOL_SIZING",
        "MAX_CRYPTO_HELD", "CRYPTO_DOLLARS_PER_BUY", "CRYPTO_STOP_LOSS_PCT",
        "DAILY_LOSS_LIMIT", "TRADE_OPTIONS", "TRADE_CRYPTO",
    ] if hasattr(settings, k)}

    # market context: SPY trend + the strongest momentum names in the universe
    market = {}
    try:
        a = analyze_all(data, list(settings.ALLOWED_STOCKS) + held_stocks + ["SPY"])
        spy = a.get("SPY", {})
        market["spy_trending_up"] = spy.get("trending_up")
        market["spy_3mo_pct"] = spy.get("mom_63d")
        ranked = rank_buys(a, exclude=set(held_stocks) | {"SPY"})[:8]
        market["top_momentum_now"] = [
            {"sym": s, "mom_63d": a[s].get("mom_63d"), "rsi": a[s].get("rsi14")}
            for s in ranked
        ]
        market["held_stock_signals"] = [
            {"sym": s, "trending_up": a[s].get("trending_up"),
             "mom_63d": a[s].get("mom_63d"), "rsi": a[s].get("rsi14"),
             "atr_pct": a[s].get("atr_pct")}
            for s in held_stocks if s in a and a[s].get("enough_data")
        ]
    except Exception as e:
        market["_error"] = str(e)[:200]

    # news headlines for what we hold (stocks only)
    headlines = {}
    for sym in held_stocks[:6]:
        try:
            items = news.get_news(NewsRequest(
                symbols=sym, start=datetime.now(timezone.utc) - timedelta(days=3), limit=4,
            )).data.get("news", [])
            headlines[sym] = [f"{n.created_at.date()}: {n.headline}" for n in items]
        except Exception:
            pass

    # the last few daily notes, so the analyst can build on its own thinking
    prior = []
    for f in sorted(glob.glob(os.path.join(RESEARCH_DIR, "20*.md")))[-3:]:
        with open(f) as fh:
            prior.append(fh.read()[:2500])

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "account": {
            "label": PROFILE["label"], "equity": round(equity, 2), "cash": round(cash, 2),
            "start_equity": round(start_equity, 2) if start_equity else None,
            "since_start": round(equity - start_equity, 2) if start_equity else None,
            "since_start_pct": round((equity / start_equity - 1) * 100, 2) if start_equity else None,
            "today_change": round(day_change, 2),
        },
        "positions": positions,
        "completed_trades_vs_spy": trades,
        "signal_accuracy_10d": signal,
        "_notes": {
            "signal_accuracy_10d": "grade_all() intentionally excludes crypto_sma_v1 "
            "(crypto is scored by realised P/L in completed_trades_vs_spy, not forward "
            "price accuracy) and options_long_v1 (trading is off). Their absence here is "
            "by design, not a gap.",
            "claude_advisor_v1": "advisory ONLY — it logs BUY/SELL opinions and never "
            "places an order. BUY decisions with no fill are expected and correct. Its "
            "whole purpose is the head-to-head in signal_accuracy_10d: once both it and "
            "sma_scan_v1 have judged decisions, compare their hit_rate / avg_earned_pct / "
            "beat_benchmark and say plainly whether the AI is adding anything over the "
            "mechanical scanner. If it isn't, it should be paused (AI_ADVISOR_ENABLED).",
        },
        "decisions_last_7d": decisions_7d,
        "filled_trades_last_14d": trades_14d,
        "strategy_settings": knobs,
        "market_context": market,
        "recent_news": headlines,
        "prior_review_notes": prior,
    }


SYSTEM = (
    "You are a sharp, honest quantitative analyst reviewing an automated PAPER-money "
    "trading bot once a day. It trades US stocks and crypto with a momentum / "
    "trend-following strategy (SMA crossover + 3-6 month momentum ranking, market-regime "
    "filter, ATR stops, volatility-scaled sizing, trailing stops). It is a learning "
    "project; the honest baseline is 'most simple bots lose to buying an index fund'.\n\n"
    "HOW THE STRATEGY IS DESIGNED (so you don't re-flag intended behaviour as bugs):\n"
    "- `trending_up` is a SHORT signal (5-day vs 20-day average, ~1 month). `mom_63d` / "
    "`mom_126d` are 3- and 6-month returns. They are SUPPOSED to disagree sometimes — a "
    "stock can bounce short-term inside a longer downtrend. The 'momentum-breakdown exit' "
    "(sell if `mom_63d` <= -MOMENTUM_BREAKDOWN_PCT even while `trending_up`) exists "
    "precisely to handle that divergence. A held name with `trending_up: true` and deeply "
    "negative `mom_63d` that hasn't sold yet just means the market has been closed since "
    "the rule last ran — note it once, don't treat it as a contradiction.\n"
    "- `signal_accuracy_10d` grades each decision against the price 10 trading days later. "
    "Everything reading 0 judged / all pending is EXPECTED for the first ~2 weeks of a "
    "decision's life and for the whole log while the bot is young — it is not a broken "
    "pipeline. Mention it at most once, briefly.\n"
    "- The stock robot only runs when the US market is OPEN; a multi-day gap in live "
    "stock activity over a weekend or holiday is normal. Crypto runs 24/7.\n"
    "- All decision/trade counts you're given are LIVE runs only (pretend test runs are "
    "already filtered out) — so a SELL count with no matching fill IS a real concern.\n\n"
    "Spend your analysis on what's genuinely NEW or changed since the prior notes, not "
    "on re-litigating the same structural facts every day.\n\n"
    "Write a concise daily review (~450 words, plain markdown). Do NOT put a "
    "title or top-level heading at the start — begin directly with the first "
    "section. Use exactly these four sections, each headed with a markdown H2 "
    "(`## Section Name`, NOT a bold-text line) — this matters mechanically, not "
    "just cosmetically, because a downstream script pulls the first paragraph "
    "after the heading into a summary file:\n"
    "## How it's actually going\n"
    "The real completed-trades result vs SPY. State plainly if the sample is too "
    "small to conclude anything (it usually is early on).\n"
    "## Patterns\n"
    "Anything consistent about the winners vs the losers (sector, hold time, entry "
    "type, volatility). Say 'nothing clear yet' if that's the truth.\n"
    "## Market & positioning\n"
    "What the market is doing, whether the bot's stance (invested vs cash, what it "
    "holds) fits, any news that matters.\n"
    "## Hypotheses to watch\n"
    "1 to 3 specific things worth tracking or testing (a filter, a parameter, a "
    "signal). Frame them as 'watch whether X' — NOT as instructions. Do not tell "
    "anyone to change a live setting.\n\n"
    "Be direct. No cheerleading. If the data says 'flat and noisy', say that."
)


def main():
    info = gather()
    msg = claude.messages.create(
        model=MODEL,
        max_tokens=6000,
        output_config={"effort": "medium"},
        system=SYSTEM,
        messages=[{"role": "user", "content":
                   "Here is today's data. Write the daily review.\n\n```json\n"
                   + json.dumps(info, indent=2, default=str) + "\n```"}],
    )
    body = "".join(b.text for b in msg.content if b.type == "text").strip()

    cost = round(msg.usage.input_tokens * PRICE_IN + msg.usage.output_tokens * PRICE_OUT, 4)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    acct = info["account"]
    header = (f"# Daily review — {info['as_of']}  ·  {acct['label']}\n\n"
              f"Account {_money(acct['equity'])}  ·  since start "
              f"{_money(acct['since_start'])} ({acct['since_start_pct']:+.2f}%)  ·  "
              f"today {_money(acct['today_change'])}\n\n---\n\n")

    dated = os.path.join(RESEARCH_DIR, f"{today}.md")
    with open(dated, "w") as fh:
        fh.write(header + body + "\n\n---\n\n<details><summary>raw data</summary>\n\n```json\n"
                 + json.dumps(info, indent=2, default=str) + "\n```\n</details>\n"
                 + f"\n<sub>{MODEL} · {msg.usage.input_tokens} in / "
                 + f"{msg.usage.output_tokens} out · ~${cost}</sub>\n")

    # prepend a short entry to the running journal (newest first)
    lessons = os.path.join(RESEARCH_DIR, "LESSONS.md")
    MARK = "<!-- entries below, newest first -->\n"
    HEAD = ("# Lessons — running journal\n\n"
            "One short entry per day; each links to that day's full review.\n\n" + MARK)
    def _is_heading(p):
        p = p.strip()
        # a markdown heading, or a whole paragraph that's just a bold label
        # (e.g. "**How it's actually going**") — both are section titles, not content
        return p.startswith("#") or bool(re.fullmatch(r"\*\*[^\n*]+\*\*", p))

    first_para = next((p for p in body.split("\n\n") if p.strip() and not _is_heading(p)),
                      body)[:600]
    entry = (f"\n## {today} · {acct['label']} · {_money(acct['equity'])} "
             f"({acct['since_start_pct']:+.2f}% since start)\n\n{first_para}\n\n"
             f"[full note →]({today}.md)\n")
    existing = ""
    if os.path.exists(lessons):
        with open(lessons) as fh:
            existing = fh.read()
    if MARK not in existing:
        existing = HEAD
    head, tail = existing.split(MARK, 1)
    # drop any earlier entry for the same day (re-runs shouldn't pile up)
    tail = re.sub(rf"\n## {today} .*?(?=\n## \d|\Z)", "", tail, flags=re.S)
    with open(lessons, "w") as fh:
        fh.write(head + MARK + entry + tail)

    print(f"wrote {dated}")
    print(f"cost ~${cost}  ({msg.usage.input_tokens} in / {msg.usage.output_tokens} out)")
    print("\n" + body[:800] + ("..." if len(body) > 800 else ""))


if __name__ == "__main__":
    main()
