"""
STEP 11: Trade options (paper money) — buy calls and puts only, "stock-replacement" style.

We buy DEEP IN THE MONEY, FAR from expiry (see settings.py) so the contract
barely bleeds to time-decay and moves almost like the stock — a leveraged way
to ride a trend, not a lottery ticket.

Each run:
  1. Look at every option bet we hold. Sell to close if the trend that
     justified it has reversed (the same 5/20 SMA signal the stock robot uses),
     OR it's down past the disaster stop, OR expiry is close.
     There is NO fixed profit target — winners are allowed to run.
  2. Scan the big list for STRONG fresh crossovers (real 5-day momentum) that
     agree with the market's direction (SPY). Call on up, put on down.
  Every trade checks the options bouncer first. Everything is logged.

We NEVER sell an option to open. Worst case on any bet = what we paid.

Run it like this:
    ./venv/bin/python step11_options.py
    ./venv/bin/python step11_options.py --pretend    (talk only, no trades)
"""

import os
import sys
import time
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionLatestQuoteRequest

import settings
import diary
from scanner import analyze_all
from safety import can_i_trade_option
import options_engine as opt

load_dotenv()
K = os.getenv("ALPACA_API_KEY")
S = os.getenv("ALPACA_SECRET_KEY")

just_talking = "--pretend" in sys.argv
mode = "pretend" if just_talking else "live"

trading = TradingClient(K, S, paper=True)
stock_data = StockHistoricalDataClient(K, S)
odc = OptionHistoricalDataClient(K, S)
db = diary.get_db()

def option_positions():
    return [p for p in trading.get_all_positions()
            if str(getattr(p, "asset_class", "")).lower().endswith("us_option")]


# When options are turned OFF we still do one job: close out anything we already
# hold (wind-down mode). We never open new bets. Once the book is empty, nothing.
OPTIONS_OFF = not settings.TRADE_OPTIONS
if OPTIONS_OFF and not option_positions():
    print("Options trading is off (TRADE_OPTIONS = False) and no bets are open. Nothing to do.")
    raise SystemExit(0)
if OPTIONS_OFF:
    print("Options trading is OFF — this run only CLOSES existing bets, opens nothing.")

# Options orders only fill during market hours — don't leave orders queued overnight.
if not just_talking and not trading.get_clock().is_open:
    print("Market is closed — the options robot only runs while the market is open.")
    raise SystemExit(0)


def option_bid(symbol):
    q = odc.get_option_latest_quote(OptionLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
    return q.bid_price, q.ask_price


def wait_for_fill(order):
    for _ in range(12):
        time.sleep(1)
        order = trading.get_order_by_id(order.id)
        if order.status == "filled":
            return "filled", float(order.filled_avg_price), str(order.id)
    # limit order didn't fill in time — cancel it, don't leave it resting in the book
    try:
        trading.cancel_order_by_id(order.id)
        time.sleep(1)
        order = trading.get_order_by_id(order.id)
        if order.status == "filled":
            return "filled", float(order.filled_avg_price), str(order.id)
    except Exception:
        pass
    return "not_filled", None, str(order.id)


def record(run_id, underlying, action, reason, owned, stock_price, ctx):
    ctx = dict(ctx)
    ctx["strategy"] = opt.STRATEGY_NAME
    ctx["mode"] = mode
    return diary.log_decision(db, run_id, underlying, action, reason, owned,
                              None, None, stock_price, ctx)


# ---- start --------------------------------------------------------
acct = trading.get_account()
equity_before, cash_before = float(acct.equity), float(acct.cash)
run_id = diary.start_run(db, mode, opt.STRATEGY_NAME, equity_before, cash_before)

held = option_positions()
held_unders = [opt.parse_occ(p.symbol)["underlying"] for p in held if opt.parse_occ(p.symbol)]

print("=" * 60)
print(f"OPTIONS RUN #{run_id}   mode: {mode}   holding {len(held)} option bet(s)")
print("=" * 60)

# one SMA scan, used for BOTH exits ("has the trend reversed?") and entries
analysis = analyze_all(stock_data, list(settings.ALLOWED_STOCKS) + held_unders + ["SPY"])
spy = analysis.get("SPY", {})
spy_up = bool(spy.get("enough_data") and spy.get("trending_up"))

# ---- 1. EXIT pass -----------------------------------------------
print("\n--- checking option bets we hold ---")
for pos in held:
    info = opt.parse_occ(pos.symbol)
    name = opt.readable(pos.symbol)
    entry = float(pos.avg_entry_price)          # premium per share
    contracts = abs(int(float(pos.qty)))
    bid, ask = option_bid(pos.symbol)
    now_val = bid if bid else 0.0
    pnl_pct = ((now_val - entry) / entry * 100) if entry else 0.0
    dte = opt.days_to_expiry(pos.symbol)
    a = analysis.get(info["underlying"], {})
    kind = info["kind"]                         # "call" or "put"

    ctx = {"contract": pos.symbol, "readable": name, "entry_premium": entry,
           "current_bid": bid, "pnl_pct": round(pnl_pct, 1), "days_to_expiry": dte,
           "contracts": contracts, "underlying_trending_up": a.get("trending_up"),
           "underlying_sell_signal": a.get("sell_signal")}

    reasons = []
    if OPTIONS_OFF:
        reasons.append("options trading turned off — closing out")
    else:
        # MAIN exit: the trend that justified the bet has turned against us
        if a.get("enough_data"):
            if kind == "call" and a.get("sell_signal"):
                reasons.append(f"{info['underlying']} trend turned down — thesis over")
            if kind == "put" and a.get("trending_up"):
                reasons.append(f"{info['underlying']} trend turned back up — thesis over")
        # FLOOR: disaster stop
        if pnl_pct <= -settings.OPTION_DISASTER_STOP_PCT:
            reasons.append(f"down {pnl_pct:.0f}% (disaster stop)")
        # TIME: don't hold into the theta cliff
        if dte is not None and dte <= settings.OPTION_CLOSE_BEFORE_EXPIRY_DAYS:
            reasons.append(f"only {dte} days to expiry")

    if not reasons:
        record(run_id, info["underlying"], "WAIT",
               f"Hold {name}: {pnl_pct:+.0f}%, {dte} days left, trend still with us.", True, None, ctx)
        print(f"  {name}: hold ({pnl_pct:+.0f}%, {dte}d left)")
        continue

    reason = f"Close {name}: " + ", ".join(reasons) + "."
    decision_id = record(run_id, info["underlying"], "SELL", reason, True, None, ctx)
    print(f"  {name}: SELL -> {reason}")

    ok, why = can_i_trade_option(trading, pos.symbol, info["underlying"], contracts, entry * 100, "sell")
    if not ok:
        diary.log_trade(db, run_id, decision_id, info["underlying"], "sell", "blocked",
                        shares=contracts, note=f"{pos.symbol} | {why}",
                        equity_before=equity_before, cash_before=cash_before)
        continue
    if just_talking:
        diary.log_trade(db, run_id, decision_id, info["underlying"], "sell", "pretend",
                        shares=contracts, fill_price=bid, note=f"{pos.symbol} | {name}",
                        equity_before=equity_before, cash_before=cash_before)
        print(f"    WOULD sell to close {contracts}x")
        continue
    order = opt.sell_to_close(trading, pos.symbol, contracts, bid or 0.05)
    status, fill, oid = wait_for_fill(order)
    diary.log_trade(db, run_id, decision_id, info["underlying"], "sell", status,
                    shares=contracts, fill_price=fill, order_id=oid,
                    note=f"{pos.symbol} | {name}",
                    equity_before=equity_before, cash_before=cash_before)
    print(f"    {status}" + (f" @ ${fill:,.2f} (${fill*100*contracts:,.2f})" if fill else ""))

# ---- 2. ENTRY pass -------------------------------------------
held = option_positions()
open_underlyings = {opt.parse_occ(p.symbol)["underlying"] for p in held if opt.parse_occ(p.symbol)}
room = 0 if OPTIONS_OFF else settings.MAX_OPTION_POSITIONS - len(held)

print(f"\n--- scanning for new option bets (room for {max(room,0)}) ---")
if OPTIONS_OFF:
    print("  options are off — opening nothing.")
elif room <= 0:
    print("  no room — already at the limit.")
else:
    mom = settings.OPTION_MIN_MOMENTUM_PCT
    # only STRONG fresh crossovers — real momentum behind them, not a wiggle
    bullish = sorted(
        [(s, a) for s, a in analysis.items()
         if s != "SPY" and a.get("enough_data") and a["crossed_up"]
         and a["move_5d_pct"] >= mom],
        key=lambda t: -t[1]["move_5d_pct"])
    bearish = sorted(
        [(s, a) for s, a in analysis.items()
         if s != "SPY" and a.get("enough_data") and a["crossed_down"]
         and a["move_5d_pct"] <= -mom],
        key=lambda t: t[1]["move_5d_pct"])

    # don't fight the market: calls only when SPY trends up, puts only when it doesn't
    if settings.OPTION_USE_MARKET_FILTER:
        if spy_up:
            bearish = []
            print("  SPY trending up → calls only")
        else:
            bullish = []
            print("  SPY not trending up → puts only")

    # interleave: call, put, call, put...
    queue = []
    for i in range(max(len(bullish), len(bearish))):
        if i < len(bullish): queue.append(("call", *bullish[i]))
        if i < len(bearish): queue.append(("put", *bearish[i]))

    print(f"  {len(bullish)} strong bullish, {len(bearish)} strong bearish (≥{mom:g}% in 5d)")

    made = 0
    for direction, sym, a in queue:
        if made >= room:
            break
        if sym in open_underlyings:
            continue
        stock_price = a["price"]
        contract = opt.pick_contract(trading, odc, sym, direction, stock_price)
        if not contract:
            print(f"  {sym} {direction}: no good contract found, skip")
            continue

        cost = contract["cost_1_contract"]
        reason = (f"{sym} strong {'up' if direction == 'call' else 'down'} crossover "
                  f"(5d move {a['move_5d_pct']:+.1f}%), SPY agrees. Buy 1 deep-ITM "
                  f"{contract['underlying']} ${contract['strike']:g} {direction} "
                  f"exp {contract['expiration']} for ~${cost:,.0f}.")
        decision_id = record(run_id, sym, "BUY", reason, False, stock_price, {"contract_pick": contract})
        print(f"  {sym} {direction}: {reason}")

        if cost > settings.MAX_DOLLARS_PER_OPTION:
            diary.log_trade(db, run_id, decision_id, sym, "buy", "skipped",
                            note=f"{contract['symbol']} | costs ${cost:,.0f}, over budget",
                            equity_before=equity_before, cash_before=cash_before)
            print("    skip (too expensive for one contract)")
            continue

        ok, why = can_i_trade_option(trading, contract["symbol"], sym, 1, cost, "buy")
        if not ok:
            diary.log_trade(db, run_id, decision_id, sym, "buy", "blocked",
                            note=f"{contract['symbol']} | {why}",
                            equity_before=equity_before, cash_before=cash_before)
            print(f"    bouncer blocked: {why}")
            continue

        if just_talking:
            diary.log_trade(db, run_id, decision_id, sym, "buy", "pretend", shares=1,
                            fill_price=contract["ask"], note=f"{contract['symbol']} | ~${cost:,.0f}",
                            equity_before=equity_before, cash_before=cash_before)
            print(f"    WOULD buy 1 contract (~${cost:,.0f})")
            made += 1
            continue

        order = opt.buy_to_open(trading, contract["symbol"], 1, contract["ask"])
        status, fill, oid = wait_for_fill(order)
        diary.log_trade(db, run_id, decision_id, sym, "buy", status, shares=1,
                        fill_price=fill, order_id=oid,
                        note=f"{contract['symbol']} | {opt.readable(contract['symbol'])}",
                        equity_before=equity_before, cash_before=cash_before)
        if fill:
            print(f"    bought 1 @ ${fill:,.2f} (${fill*100:,.2f})")
            made += 1
        else:
            print(f"    {status}")

# ---- done ---------------------------------------------------
acct = trading.get_account()
diary.finish_run(db, run_id, float(acct.equity), float(acct.cash))

print("\n" + "=" * 60)
opts_now = option_positions()
if opts_now:
    print("Option bets held:")
    for p in opts_now:
        pl = float(p.unrealized_pl)
        print(f"  {p.qty}x {opt.readable(p.symbol)}  "
              f"value ${float(p.market_value):,.2f}  ({'+' if pl >= 0 else ''}{pl:,.2f})")
else:
    print("No option bets held.")
print(f"\nSaved to {os.path.basename(diary.DB_PATH)} as run #{run_id}.")
