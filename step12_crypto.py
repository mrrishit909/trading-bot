"""
STEP 12: Trade crypto (paper money). This one runs 24/7 — crypto never closes.

Each run:
  1. Look at every coin we hold. If it stopped trending up, SELL it.
  2. Scan the crypto list. Buy the ones trending up (fresh crossovers first),
     up to MAX_CRYPTO_HELD coins.
  Every trade checks the crypto bouncer first. Everything is logged.

Run it like this:
    ./venv/bin/python step12_crypto.py
    ./venv/bin/python step12_crypto.py --pretend    (talk only, no trades)
"""

import os
import sys
import time
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoLatestQuoteRequest

import settings
import diary
from crypto_scanner import analyze_all, rank_buys, STRATEGY_NAME
from safety import can_i_trade_crypto

load_dotenv()
K = os.getenv("ALPACA_API_KEY")
S = os.getenv("ALPACA_SECRET_KEY")

just_talking = "--pretend" in sys.argv
mode = "pretend" if just_talking else "live"

trading = TradingClient(K, S, paper=True)
cdc = CryptoHistoricalDataClient()
db = diary.get_db()

if not settings.TRADE_CRYPTO:
    print("Crypto trading is switched off in settings.py (TRADE_CRYPTO = False).")
    raise SystemExit(0)


def norm(s):
    """Position symbols come back as 'BTCUSD'; data/orders use 'BTC/USD'."""
    s = str(s)
    return s if "/" in s else (s[:-3] + "/USD" if s.endswith("USD") else s)


def crypto_positions():
    return [p for p in trading.get_all_positions()
            if str(getattr(p, "asset_class", "")).lower().endswith("crypto")]


def price_now(symbol):
    q = cdc.get_crypto_latest_quote(CryptoLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
    return q.ask_price or q.bid_price


def wait_for_fill(order):
    for _ in range(10):
        time.sleep(1)
        order = trading.get_order_by_id(order.id)
        if order.status == "filled":
            return "filled", float(order.filled_avg_price), float(order.filled_qty), str(order.id)
    return "not_filled", None, None, str(order.id)


def record(run_id, symbol, action, reason, owned, a, ref_price):
    ctx = dict(a)
    ctx["strategy"] = STRATEGY_NAME
    ctx["mode"] = mode
    return diary.log_decision(db, run_id, symbol, action, reason, owned,
                              a.get("fast"), a.get("slow"), ref_price, ctx)


# ---- start ------------------------------------------------------
acct = trading.get_account()
equity_before, cash_before = float(acct.equity), float(acct.cash)
run_id = diary.start_run(db, mode, STRATEGY_NAME, equity_before, cash_before)

held = crypto_positions()
held_syms = {norm(p.symbol) for p in held}
analysis = analyze_all(cdc, settings.CRYPTO_UNIVERSE)

print("=" * 58)
print(f"CRYPTO RUN #{run_id}   mode: {mode}   holding {len(held)} coin(s)")
print("=" * 58)

# ---- 1. SELL pass --------------------------------------------
print("\n--- checking coins we hold ---")
for pos in held:
    sym = norm(pos.symbol)
    a = analysis.get(sym, {"enough_data": False})
    ref = price_now(sym)
    if a.get("enough_data") and a.get("trending_up"):
        record(run_id, sym, "WAIT", f"{sym} still trending up. Keep holding.", True, a, ref)
        print(f"  {sym}: keep (trending up)")
        continue

    reason = f"{sym} no longer trending up (3d avg below 10d avg). Sell."
    decision_id = record(run_id, sym, "SELL", reason, True, a, ref)
    print(f"  {sym}: SELL -> {reason}")
    qty = abs(float(pos.qty))

    ok, why = can_i_trade_crypto(trading, sym, qty * ref, "sell")
    if not ok:
        diary.log_trade(db, run_id, decision_id, sym, "sell", "blocked", shares=qty, note=why,
                        equity_before=equity_before, cash_before=cash_before)
        print(f"    bouncer blocked: {why}")
        continue
    if just_talking:
        diary.log_trade(db, run_id, decision_id, sym, "sell", "pretend", shares=qty, fill_price=ref,
                        equity_before=equity_before, cash_before=cash_before)
        print(f"    WOULD sell {qty:g} {sym}")
        continue
    order = trading.submit_order(MarketOrderRequest(
        symbol=sym, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.GTC))
    status, fill, fqty, oid = wait_for_fill(order)
    diary.log_trade(db, run_id, decision_id, sym, "sell", status, shares=fqty or qty,
                    fill_price=fill, order_id=oid,
                    equity_before=equity_before, cash_before=cash_before)
    print(f"    {status}" + (f" @ ${fill:,.2f}" if fill else ""))

# ---- 2. BUY pass --------------------------------------------
held = crypto_positions()
held_syms = {norm(p.symbol) for p in held}
room = settings.MAX_CRYPTO_HELD - len(held)
shortlist = rank_buys(analysis, exclude=held_syms)

print(f"\n--- scan: {len(shortlist)} coins trending up; room for {max(room,0)} ---")
print(f"    shortlist: {', '.join(shortlist) or '(none)'}")

bought = 0
for sym in shortlist:
    if bought >= room:
        a = analysis[sym]
        record(run_id, sym, "WAIT", f"{sym} trending up but no room (hold {len(held)}).", False, a, a["price"])
        continue
    a = analysis[sym]
    ref = price_now(sym)
    tag = "just crossed up" if a["crossed_up"] else "trending up"
    reason = f"{sym} {tag} (3d ${a['fast']:,.2f} vs 10d ${a['slow']:,.2f}), {a['move_5d_pct']:+.1f}% in 5 days."
    decision_id = record(run_id, sym, "BUY", reason, False, a, ref)
    print(f"  {sym}: BUY -> {reason}")

    dollars = settings.CRYPTO_DOLLARS_PER_BUY
    ok, why = can_i_trade_crypto(trading, sym, dollars, "buy")
    if not ok:
        diary.log_trade(db, run_id, decision_id, sym, "buy", "blocked", note=why,
                        equity_before=equity_before, cash_before=cash_before)
        print(f"    bouncer blocked: {why}")
        continue
    if just_talking:
        diary.log_trade(db, run_id, decision_id, sym, "buy", "pretend",
                        shares=round(dollars / ref, 8), fill_price=ref,
                        equity_before=equity_before, cash_before=cash_before)
        print(f"    WOULD buy ~${dollars} of {sym}")
        bought += 1
        continue
    order = trading.submit_order(MarketOrderRequest(
        symbol=sym, notional=dollars, side=OrderSide.BUY, time_in_force=TimeInForce.GTC))
    status, fill, fqty, oid = wait_for_fill(order)
    diary.log_trade(db, run_id, decision_id, sym, "buy", status, shares=fqty,
                    fill_price=fill, order_id=oid,
                    equity_before=equity_before, cash_before=cash_before)
    if status == "filled":
        print(f"    bought {fqty:g} {sym} @ ${fill:,.2f}  (~${dollars})")
        bought += 1
    else:
        print(f"    {status}")

# ---- done --------------------------------------------------
acct = trading.get_account()
diary.finish_run(db, run_id, float(acct.equity), float(acct.cash))

print("\n" + "=" * 58)
coins = crypto_positions()
if coins:
    print("Coins held:")
    for p in coins:
        pl = float(p.unrealized_pl)
        print(f"  {p.qty} {norm(p.symbol)}  ${float(p.market_value):,.2f}  ({'+' if pl >= 0 else ''}{pl:,.2f})")
else:
    print("No coins held.")
print(f"\nSaved to diary.db as run #{run_id}.")
