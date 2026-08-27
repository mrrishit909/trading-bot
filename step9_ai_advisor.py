"""
STEP 9: Run the AI brain in ADVISORY mode.

The AI looks at each stock and says what it WOULD do and why. It does NOT
trade. Everything goes into the same diary.db (with strategy 'claude_advisor_v1')
so later we can compare the AI's calls to:
  - what the dumb average-crossover robot said
  - what the price actually did afterwards

Run it like this:
    ./venv/bin/python step9_ai_advisor.py
"""

import os
from dotenv import load_dotenv
import anthropic
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import StockLatestQuoteRequest

import settings
from ai_brain import advise, STRATEGY_NAME
import diary

load_dotenv()
ALPACA_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")

trading = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=True)
data = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
news = NewsClient(ALPACA_KEY, ALPACA_SECRET)
claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
db = diary.get_db()


def do_we_own(symbol):
    try:
        trading.get_open_position(symbol)
        return True
    except Exception:
        return False


acct = trading.get_account()
equity_before = float(acct.equity)
cash_before = float(acct.cash)
run_id = diary.start_run(db, "ai_advisory", STRATEGY_NAME, equity_before, cash_before)

print("=" * 58)
print(f"AI ADVISOR RUN #{run_id}   (advisory only — no trades)")
print("=" * 58)

total_cost = 0.0
for symbol in settings.ALLOWED_STOCKS:
    print(f"\n--- {symbol} ---")
    own = do_we_own(symbol)

    plan = advise(data, news, claude, symbol, own)
    ctx = plan["context"]

    quote = data.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
    ref_price = quote.ask_price or quote.bid_price

    decision_id = diary.log_decision(
        db, run_id, symbol, plan["action"], plan["reason"], own,
        plan.get("fast"), plan.get("slow"), ref_price, ctx,
    )

    conf = ctx.get("ai_confidence")
    cost = ctx.get("cost_usd_est", 0) or 0
    total_cost += cost

    print(f"AI says: {plan['action']}" + (f"  (confidence {conf})" if conf is not None else ""))
    print(f"Reason: {plan['reason']}")
    print(f"(this call cost about ${cost:.4f})")

    # log what it WOULD do, but never actually trade
    if plan["action"] in ("BUY", "SELL"):
        diary.log_trade(db, run_id, decision_id, symbol, plan["action"].lower(),
                        "advisory", fill_price=ref_price, note="advisory only, not executed",
                        equity_before=equity_before, cash_before=cash_before)

diary.finish_run(db, run_id, equity_before, cash_before)

print("\n" + "=" * 58)
print(f"Done. Total AI cost this run: about ${total_cost:.4f}")
print(f"Saved to diary.db as run #{run_id}. See it with:  ./venv/bin/python show_diary.py decisions")
