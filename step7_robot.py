"""
STEP 7: The robot, now with a diary.

Same robot as step 6, but now EVERYTHING gets written into diary.db:
  - the run itself (when, live or pretend, account value before/after)
  - every decision (BUY/SELL/WAIT, why, the prices it looked at)
  - every trade attempt (filled / blocked by bouncer / skipped / pretend)

Nothing is ever deleted. This is the file we'll use later to judge the robot
and to compare it against the AI version.

Run it like this:
    ./venv/bin/python step7_robot.py             (really makes pretend-money trades)
    ./venv/bin/python step7_robot.py --pretend   (just talk, log decisions, no trades)
"""

import os
import sys
import time
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

import settings
from robot import decide, STRATEGY_NAME
from safety import can_i_trade
import diary

DOLLARS_PER_BUY = 1000

load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

just_talking = "--pretend" in sys.argv
mode = "pretend" if just_talking else "live"

trading = TradingClient(API_KEY, SECRET_KEY, paper=True)
data = StockHistoricalDataClient(API_KEY, SECRET_KEY)
db = diary.get_db()


def do_we_own(symbol):
    try:
        return trading.get_open_position(symbol)
    except Exception:
        return None


def get_quote(symbol):
    return data.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]


def make_trade(symbol, side, shares):
    """Place the order, wait for fill. Returns (status, fill_price, order_id)."""
    order = trading.submit_order(MarketOrderRequest(
        symbol=symbol, qty=shares,
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    ))
    for _ in range(12):
        time.sleep(1)
        order = trading.get_order_by_id(order.id)
        if order.status == "filled":
            return "filled", float(order.filled_avg_price), str(order.id)
    return "not_filled", None, str(order.id)


# ---- start the run -------------------------------------------------------
acct = trading.get_account()
equity_before = float(acct.equity)
cash_before = float(acct.cash)
run_id = diary.start_run(db, mode, STRATEGY_NAME, equity_before, cash_before)

print("=" * 55)
print(f"ROBOT RUN #{run_id}   mode: {mode}   strategy: {STRATEGY_NAME}")
print(f"Account before:  ${equity_before:,.2f}   cash ${cash_before:,.2f}")
print("=" * 55)

for symbol in settings.ALLOWED_STOCKS:
    print(f"\n--- {symbol} ---")
    position = do_we_own(symbol)
    own = position is not None

    plan = decide(data, symbol, own)
    quote = get_quote(symbol)
    ref_price = quote.ask_price or quote.bid_price

    ctx = plan["context"]
    ctx["bid"] = quote.bid_price
    ctx["ask"] = quote.ask_price
    ctx["mode"] = mode

    decision_id = diary.log_decision(
        db, run_id, symbol, plan["action"], plan["reason"], own,
        plan.get("fast"), plan.get("slow"), ref_price, ctx,
    )

    print(f"Decision: {plan['action']}")
    print(f"Why: {plan['reason']}")

    if plan["action"] == "WAIT":
        continue

    # Work out the trade
    if plan["action"] == "BUY":
        side = "buy"
        shares = int(DOLLARS_PER_BUY // ref_price)
        if shares < 1:
            msg = f"one share costs ${ref_price:,.2f}, over our ${DOLLARS_PER_BUY} budget"
            print(f"Skip: {msg}")
            diary.log_trade(db, run_id, decision_id, symbol, side, "skipped",
                            note=msg, equity_before=equity_before, cash_before=cash_before)
            continue
    else:  # SELL
        side = "sell"
        shares = float(position.qty)

    # Ask the bouncer
    ok, reason = can_i_trade(trading, symbol, shares, ref_price, side)
    if not ok:
        print(f"Bouncer blocked it: {reason}")
        diary.log_trade(db, run_id, decision_id, symbol, side, "blocked",
                        shares=shares, note=reason,
                        equity_before=equity_before, cash_before=cash_before)
        continue

    if just_talking:
        print(f"WOULD {side} {shares:g} {symbol} (~${shares * ref_price:,.2f})")
        diary.log_trade(db, run_id, decision_id, symbol, side, "pretend",
                        shares=shares, fill_price=ref_price,
                        equity_before=equity_before, cash_before=cash_before)
        continue

    # Do it for real (pretend money)
    print("Bouncer said yes. Trading...")
    status, fill_price, order_id = make_trade(symbol, side, shares)
    diary.log_trade(db, run_id, decision_id, symbol, side, status,
                    shares=shares, fill_price=fill_price, order_id=order_id,
                    equity_before=equity_before, cash_before=cash_before)
    if status == "filled":
        print(f"{side.upper()} {shares:g} {symbol} @ ${fill_price:,.2f}")
    else:
        print(f"Order not filled yet (status logged as '{status}').")

# ---- finish the run ----------------------------------------------------
acct = trading.get_account()
equity_after = float(acct.equity)
cash_after = float(acct.cash)
diary.finish_run(db, run_id, equity_after, cash_after)

print("\n" + "=" * 55)
print(f"Account after:  ${equity_after:,.2f}   cash ${cash_after:,.2f}")
positions = trading.get_all_positions()
if positions:
    print("Holding:")
    for p in positions:
        pl = float(p.unrealized_pl)
        print(f"  {p.qty} {p.symbol}  ${float(p.market_value):,.2f}  ({'+' if pl >= 0 else ''}{pl:,.2f})")
else:
    print("Holding: nothing (all cash)")
print(f"\nAll of this was written to diary.db (run #{run_id}).")
