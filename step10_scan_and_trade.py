"""
STEP 10: Scan the whole big list, then trade the worthy ones.

Each run the robot does this:
  1. Look at everything we currently own. If a stock has stopped trending up,
     SELL it.
  2. Scan the whole big list. Pick the top few that are trending up
     (fresh "just crossed up" signals rank highest).
  3. For each pick, if we have room (max 5 stocks held), BUY a little.
  Every step checks with the safety bouncer first. Everything is logged.

This really places PRETEND-money trades. Run it like this:
    ./venv/bin/python step10_scan_and_trade.py
    ./venv/bin/python step10_scan_and_trade.py --pretend    (talk only, no trades)
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
from scanner import analyze_all, rank_buys, STRATEGY_NAME
from safety import can_i_trade
import diary

load_dotenv()
ALPACA_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")

just_talking = "--pretend" in sys.argv
mode = "pretend" if just_talking else "live"

trading = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=True)
data = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
db = diary.get_db()


def held_positions():
    return {p.symbol: p for p in trading.get_all_positions()}


def price_now(symbol):
    q = data.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
    return q.ask_price or q.bid_price


def do_order(symbol, side, shares):
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


def record(run_id, symbol, action, reason, owned, a, ref_price):
    ctx = dict(a)
    ctx["strategy"] = STRATEGY_NAME
    ctx["mode"] = mode
    return diary.log_decision(db, run_id, symbol, action, reason, owned,
                              a.get("fast"), a.get("slow"), ref_price, ctx)


# ---- start ----------------------------------------------------------
acct = trading.get_account()
equity_before, cash_before = float(acct.equity), float(acct.cash)
run_id = diary.start_run(db, mode, STRATEGY_NAME, equity_before, cash_before)

held = held_positions()
analysis = analyze_all(data, list(settings.ALLOWED_STOCKS) + list(held))

print("=" * 60)
print(f"SCAN & TRADE RUN #{run_id}   mode: {mode}")
print(f"Big list: {len(settings.ALLOWED_STOCKS)} stocks   Currently holding: {len(held)}")
print("=" * 60)

# ---- 1. SELL pass: check everything we own -------------------------
print("\n--- checking what we own ---")
for symbol, pos in list(held.items()):
    a = analysis.get(symbol, {"enough_data": False})
    ref = price_now(symbol)
    still_good = a.get("enough_data") and a.get("trending_up")

    if still_good:
        record(run_id, symbol, "WAIT", f"{symbol} still trending up. Keep holding.", True, a, ref)
        print(f"  {symbol}: keep (trending up)")
        continue

    reason = f"{symbol} is no longer trending up (5d avg below 20d avg). Sell."
    decision_id = record(run_id, symbol, "SELL", reason, True, a, ref)
    print(f"  {symbol}: SELL -> {reason}")

    shares = float(pos.qty)
    ok, why = can_i_trade(trading, symbol, shares, ref, "sell")
    if not ok:
        diary.log_trade(db, run_id, decision_id, symbol, "sell", "blocked", shares=shares,
                        note=why, equity_before=equity_before, cash_before=cash_before)
        print(f"    bouncer blocked: {why}")
        continue
    if just_talking:
        diary.log_trade(db, run_id, decision_id, symbol, "sell", "pretend", shares=shares,
                        fill_price=ref, equity_before=equity_before, cash_before=cash_before)
        print(f"    WOULD sell {shares:g} {symbol}")
    else:
        status, fill, oid = do_order(symbol, "sell", shares)
        diary.log_trade(db, run_id, decision_id, symbol, "sell", status, shares=shares,
                        fill_price=fill, order_id=oid,
                        equity_before=equity_before, cash_before=cash_before)
        print(f"    {status} {shares:g} {symbol}" + (f" @ ${fill:,.2f}" if fill else ""))

# ---- 2. BUY pass: scan the big list ------------------------------
held = held_positions()   # refresh after sells
room = settings.MAX_STOCKS_HELD - len(held)
shortlist = rank_buys(analysis, exclude=held)[:settings.SHORTLIST_SIZE]

print(f"\n--- scan found {len(shortlist)} candidates; room for {max(room,0)} more ---")
print(f"    shortlist: {', '.join(shortlist) or '(none)'}")

bought = 0
for symbol in shortlist:
    a = analysis[symbol]
    ref = price_now(symbol)
    tag = "just crossed up" if a["crossed_up"] else "trending up"
    reason = f"{symbol} {tag} (5d ${a['fast']:,.2f} vs 20d ${a['slow']:,.2f}), +{a['move_5d_pct']}% in 5 days."

    if bought >= room:
        record(run_id, symbol, "WAIT", f"{reason} But no room (already hold {len(held)}).", False, a, ref)
        print(f"  {symbol}: skip (no room)")
        continue

    decision_id = record(run_id, symbol, "BUY", reason, False, a, ref)
    shares = int(settings.DOLLARS_PER_BUY // ref)
    if shares < 1:
        diary.log_trade(db, run_id, decision_id, symbol, "buy", "skipped",
                        note=f"one share ${ref:,.2f} over budget",
                        equity_before=equity_before, cash_before=cash_before)
        print(f"  {symbol}: skip (too pricey)")
        continue

    ok, why = can_i_trade(trading, symbol, shares, ref, "buy")
    if not ok:
        diary.log_trade(db, run_id, decision_id, symbol, "buy", "blocked", shares=shares,
                        note=why, equity_before=equity_before, cash_before=cash_before)
        print(f"  {symbol}: bouncer blocked -> {why}")
        continue

    if just_talking:
        diary.log_trade(db, run_id, decision_id, symbol, "buy", "pretend", shares=shares,
                        fill_price=ref, equity_before=equity_before, cash_before=cash_before)
        print(f"  {symbol}: WOULD buy {shares} (~${shares * ref:,.2f})")
        bought += 1
    else:
        status, fill, oid = do_order(symbol, "buy", shares)
        diary.log_trade(db, run_id, decision_id, symbol, "buy", status, shares=shares,
                        fill_price=fill, order_id=oid,
                        equity_before=equity_before, cash_before=cash_before)
        print(f"  {symbol}: {status} {shares} @ ${fill:,.2f}" if fill else f"  {symbol}: {status}")
        if status == "filled":
            bought += 1

# ---- done --------------------------------------------------------
acct = trading.get_account()
equity_after, cash_after = float(acct.equity), float(acct.cash)
diary.finish_run(db, run_id, equity_after, cash_after)

print("\n" + "=" * 60)
print(f"Account: ${equity_after:,.2f}   cash ${cash_after:,.2f}")
positions = trading.get_all_positions()
if positions:
    print("Holding:")
    for p in positions:
        pl = float(p.unrealized_pl)
        print(f"  {p.qty} {p.symbol}  ${float(p.market_value):,.2f}  ({'+' if pl >= 0 else ''}{pl:,.2f})")
else:
    print("Holding: nothing (all cash)")
print(f"\nSaved to diary.db as run #{run_id}.")
