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
import json
from datetime import datetime, timezone
from collections import Counter
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

import settings
from scanner import analyze_all, rank_buys, momentum_score, STRATEGY_NAME
from safety import can_i_trade
from sectors import sector_of
from fills import confirm_fill
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
    # stocks only — skip crypto (BTCUSD) and option (OCC symbol) positions,
    # those are owned by the crypto robot and the options robot. Also skip SPY:
    # that's the cash sleeve (never a stock pick — rank_buys excludes it), and
    # must not be hit by the sell rules or use up a slot.
    return {p.symbol: p for p in trading.get_all_positions()
            if str(p.asset_class).lower().endswith("us_equity") and p.symbol != "SPY"}


SLEEVE_STRATEGY = "spy_sleeve_v1"
_sleeve_run = None


def sleeve_value():
    try:
        return float(trading.get_open_position("SPY").market_value)
    except Exception:
        return 0.0


def sleeve_trade(side, dollars, why):
    """Buy/sell ~$dollars of SPY for the cash sleeve (side 'sell' with dollars=None
    = sell it all). Logged under its own strategy so the stock scoreboard stays clean."""
    global _sleeve_run
    if _sleeve_run is None:
        _sleeve_run = diary.start_run(db, mode, SLEEVE_STRATEGY, equity_before, cash_before)
    ref = price_now("SPY")
    shares = (dollars / ref) if dollars else float(trading.get_open_position("SPY").qty)
    ok, no = can_i_trade(trading, "SPY", shares, ref, side, sleeve=True)
    if not ok:
        diary.log_trade(db, _sleeve_run, None, "SPY", side, "blocked", shares=shares, note=no)
        print(f"  sleeve: {side} blocked -> {no}")
        return False
    if just_talking:
        diary.log_trade(db, _sleeve_run, None, "SPY", side, "pretend", shares=shares, fill_price=ref, note=why)
        print(f"  sleeve: WOULD {side} ~${shares * ref:,.0f} of SPY ({why})")
        return True
    if side == "sell" and dollars is None:
        status, fill, fqty, oid = do_sell("SPY")
    else:
        status, fill, fqty, oid = do_order("SPY", side, notional=dollars)
    diary.log_trade(db, _sleeve_run, None, "SPY", side, status, shares=fqty or shares,
                    fill_price=fill, order_id=oid, note=why)
    print(f"  sleeve: {status} {side} {(fqty or shares):g} SPY" + (f" @ ${fill:,.2f}" if fill else "") + f" ({why})")
    return status == "filled"


def price_now(symbol):
    q = data.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
    return q.ask_price or q.bid_price


def do_order(symbol, side, qty=None, notional=None):
    """Market order. Buys can pass `notional` (spend $X, get a fractional share);
    sells pass `qty` (the exact share count we hold). Returns
    (status, fill_price, filled_qty, order_id)."""
    kw = {"symbol": symbol,
          "side": OrderSide.BUY if side == "buy" else OrderSide.SELL,
          "time_in_force": TimeInForce.DAY}
    if notional is not None:
        kw["notional"] = round(notional, 2)
    else:
        kw["qty"] = qty
    order = trading.submit_order(MarketOrderRequest(**kw))
    return confirm_fill(trading, order, symbol=symbol, price_fn=price_now)


def do_sell(symbol):
    """Flatten the whole position (handles fractional share counts cleanly).
    Returns (status, fill_price, filled_qty, order_id)."""
    want = None
    try:
        want = abs(float(trading.get_open_position(symbol).qty))
    except Exception:
        pass
    order = trading.close_position(symbol)
    return confirm_fill(trading, order, symbol=symbol, want_qty=want, price_fn=price_now)


def do_partial_sell(symbol, qty):
    """Sell part of a position (for scale-out). Tries a fractional qty; if the
    stock isn't fractionable, falls back to whole shares. Returns the do_order
    4-tuple, or ('skipped', ...) if it rounds to nothing."""
    try:
        return do_order(symbol, "sell", qty=round(qty, 6))
    except Exception as e:
        if any(w in str(e).lower() for w in ("fractional", "notional", "not fractionable")):
            whole = int(qty)
            if whole >= 1:
                try:
                    return do_order(symbol, "sell", qty=whole)
                except Exception:
                    return "error", None, None, None
            return "skipped", None, None, None
        return "error", None, None, None


def place_buy(symbol, dollars, ref):
    """Buy ~$dollars of the stock. Fractional (notional) if the asset allows it,
    otherwise fall back to the largest whole-share amount that fits.
    Returns (status, fill_price, filled_qty, order_id, note)."""
    try:
        s, fill, fqty, oid = do_order(symbol, "buy", notional=dollars)
        return s, fill, fqty, oid, "fractional $"
    except Exception as e:
        msg = str(e).lower()
        frac_issue = any(w in msg for w in ("fractional", "notional", "not fractionable"))
        if not frac_issue:
            return "error", None, None, None, str(e)[:120]
        whole = int(dollars // ref)
        if whole < 1:
            return "skipped", None, None, None, f"not fractionable; one share ${ref:,.0f} over budget"
        try:
            s, fill, fqty, oid = do_order(symbol, "buy", qty=whole)
            return s, fill, fqty, oid, f"not fractionable; bought {whole} whole"
        except Exception as e2:
            return "error", None, None, None, str(e2)[:120]


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
analysis = analyze_all(data, list(settings.ALLOWED_STOCKS) + list(held) + ["SPY"])

# today's pre-market news read (news_scan.py). Degrade safely if it's missing/stale.
NEWS = {"market": {"read": "neutral"}, "stocks": {}}
if getattr(settings, "USE_NEWS_FILTER", False):
    _today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _path = os.path.join(os.path.dirname(__file__), "news", f"{_today}.json")
    try:
        with open(_path) as _fh:
            _n = json.load(_fh)
        if _n.get("date") == _today:
            NEWS = _n
            print(f"news: market={NEWS['market']['read']} · {len(NEWS['stocks'])} stock verdicts")
    except (OSError, ValueError):
        print("news: no fresh pre-market scan for today — trading on the signals alone")


def news_verdict(sym):
    return NEWS["stocks"].get(sym.upper(), {}).get("verdict")


print("=" * 60)
print(f"SCAN & TRADE RUN #{run_id}   mode: {mode}")
print(f"Big list: {len(settings.ALLOWED_STOCKS)} stocks   Currently holding: {len(held)}")
print("=" * 60)

# ---- 1. SELL pass: check everything we own -------------------------
print("\n--- checking what we own ---")
for symbol, pos in list(held.items()):
    a = analysis.get(symbol, {"enough_data": False})
    ref = price_now(symbol)

    # how far below our purchase price is it right now?
    try:
        loss_pct = (ref / float(pos.avg_entry_price) - 1) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        loss_pct = 0.0

    # how far below its recent high is it right now? (only matters if we're up)
    peak = a.get("recent_high") or ref
    drawdown_pct = (ref / peak - 1) * 100 if peak else 0.0

    # stop-loss distance: volatility-adaptive (N x ATR) if we have an ATR,
    # clamped to [4%, STOCK_STOP_LOSS_PCT]; otherwise the plain fixed %.
    stop_pct = settings.STOCK_STOP_LOSS_PCT
    if getattr(settings, "USE_ATR_STOP", False) and a.get("atr_pct"):
        stop_pct = min(settings.STOCK_STOP_LOSS_PCT,
                       max(4.0, settings.STOCK_STOP_ATR_MULT * a["atr_pct"]))

    if loss_pct <= -stop_pct:
        reason = (f"{symbol} is down {loss_pct:.1f}% from what we paid "
                  f"(stop-loss is -{stop_pct:.1f}%). Sell now.")
    elif loss_pct > 0 and drawdown_pct <= -settings.TRAILING_STOP_PCT:
        reason = (f"{symbol} is up {loss_pct:.1f}% from what we paid but has fallen "
                  f"{abs(drawdown_pct):.1f}% from its recent high (${peak:,.2f}) — "
                  f"lock in the gain (trailing stop).")
    elif a.get("mom_63d") is not None and a["mom_63d"] <= -settings.MOMENTUM_BREAKDOWN_PCT:
        reason = (f"{symbol}'s 3-month momentum has broken down ({a['mom_63d']:.1f}%) — "
                  f"even though the short-term average still says trending up, this "
                  f"looks like a bounce inside a real downtrend. Sell.")
    elif news_verdict(symbol) == "avoid":
        reason = (f"{symbol} had a clear negative news catalyst overnight "
                  f"({NEWS['stocks'][symbol]['reason']}) — get out.")
    elif not a.get("enough_data") or a.get("sell_signal"):
        reason = f"{symbol} is no longer trending up (5d avg clearly below 20d avg). Sell."
    elif (getattr(settings, "SCALE_OUT_ENABLED", False)
          and loss_pct >= settings.SCALE_OUT_GAIN_PCT
          and not diary.already_scaled_out(db, STRATEGY_NAME, symbol)):
        # partial profit-take, then keep holding the rest
        frac = settings.SCALE_OUT_FRACTION
        sell_qty = float(pos.qty) * frac
        so_reason = (f"{symbol} is up {loss_pct:.1f}% — take {frac*100:.0f}% off the table "
                     f"(scale-out), let the rest run.")
        decision_id = record(run_id, symbol, "SELL", so_reason, True, a, ref)
        print(f"  {symbol}: SCALE-OUT -> {so_reason}")
        ok, why = can_i_trade(trading, symbol, sell_qty, ref, "sell")
        if not ok:
            diary.log_trade(db, run_id, decision_id, symbol, "sell", "blocked", shares=sell_qty,
                            note="scale-out; " + why, equity_before=equity_before, cash_before=cash_before)
            print(f"    bouncer blocked: {why}")
        elif just_talking:
            diary.log_trade(db, run_id, decision_id, symbol, "sell", "pretend", shares=sell_qty,
                            fill_price=ref, note="scale-out",
                            equity_before=equity_before, cash_before=cash_before)
            print(f"    WOULD scale-out {sell_qty:g} {symbol}")
        else:
            status, fill, fqty, oid = do_partial_sell(symbol, sell_qty)
            diary.log_trade(db, run_id, decision_id, symbol, "sell", status,
                            shares=fqty or sell_qty, fill_price=fill, order_id=oid, note="scale-out",
                            equity_before=equity_before, cash_before=cash_before)
            print(f"    {status} {(fqty or sell_qty):g} {symbol}" + (f" @ ${fill:,.2f}" if fill else ""))
        continue
    else:
        record(run_id, symbol, "WAIT", f"{symbol} still trending up. Keep holding.", True, a, ref)
        print(f"  {symbol}: keep")
        continue

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
        status, fill, fqty, oid = do_sell(symbol)
        diary.log_trade(db, run_id, decision_id, symbol, "sell", status, shares=fqty or shares,
                        fill_price=fill, order_id=oid,
                        equity_before=equity_before, cash_before=cash_before)
        print(f"    {status} {(fqty or shares):g} {symbol}" + (f" @ ${fill:,.2f}" if fill else ""))

# ---- 2. BUY pass: scan the big list ------------------------------
held = held_positions()   # refresh after sells
room = settings.MAX_STOCKS_HELD - len(held)

# market-regime filter: don't buy stocks while the whole market is trending down.
# Gate = SPY's own 63-day (one-quarter) return vs MARKET_TREND_MIN_MOM63.
# (Was SPY 5-day avg vs 20-day avg — too twitchy; see settings.py note.)
spy = analysis.get("SPY", {})
_spy_mom = spy.get("mom_63d")
market_ok = (
    (not settings.USE_MARKET_FILTER)
    or (not spy.get("enough_data"))
    or _spy_mom is None
    or _spy_mom >= settings.MARKET_TREND_MIN_MOM63
)
if not market_ok:
    print(f"\n--- market filter: SPY 3-month return {_spy_mom:.1f}% is below "
          f"{settings.MARKET_TREND_MIN_MOM63}% — market trending DOWN, not buying any stocks ---")
    room = 0

# volatility "risk-off" filter: don't buy into an unusually turbulent market,
# even one that's technically still trending up (SPY's own ATR%, a free VIX stand-in)
vol_ok = (not settings.USE_VOLATILITY_FILTER) or (not spy.get("atr_pct")) \
    or spy["atr_pct"] <= settings.MAX_MARKET_ATR_PCT
if market_ok and not vol_ok:
    print(f"\n--- volatility filter: SPY's ATR is {spy['atr_pct']:.2f}% "
          f"(cap {settings.MAX_MARKET_ATR_PCT}%) — market's too choppy, not buying this run ---")
    room = 0

# pre-market news filter: don't buy anything on a genuine risk-off day
if room > 0 and NEWS["market"]["read"] == "risk_off":
    print(f"\n--- news filter: market is RISK-OFF ({NEWS['market'].get('reason','')}) "
          f"— not buying any stocks today ---")
    room = 0

# re-buy cooldown: names we sold in the last few days are off the table
cooling = diary.recently_sold(db, STRATEGY_NAME, settings.REBUY_COOLDOWN_DAYS)

shortlist = rank_buys(analysis, exclude=set(held) | cooling | {"SPY"})[:settings.SHORTLIST_SIZE]

# rank-based rotation: room is 0 (book is full) but the best waiting candidate
# clearly outranks the weakest thing we hold -> sell the weakest, make room.
# Deliberately NOT sector-matched: the freed slot goes through the normal BUY
# loop below, which already enforces the sector cap. If the weakest-held name's
# sector is already at/over MAX_STOCKS_PER_SECTOR, freeing it also nudges that
# sector back toward the cap over time (self-heals a sector that crept over
# from trades made before the cap existed) rather than perpetuating it by
# swapping in another name from the same already-full sector.
rotate_plan = None
if (room <= 0 and market_ok and vol_ok and getattr(settings, "USE_RANK_ROTATION", False)
        and shortlist and held):
    best_new = shortlist[0]
    best_score = momentum_score(analysis[best_new])
    scored_held = sorted(
        ((momentum_score(analysis[s]), s) for s in held if analysis.get(s, {}).get("enough_data")),
        key=lambda t: t[0],
    )
    for weakest_score, weakest_sym in scored_held:
        if best_score - weakest_score < settings.ROTATION_MARGIN_PTS:
            break   # sorted ascending — if the weakest doesn't clear the bar, none will
        bought_ts = diary.last_buy_ts(db, STRATEGY_NAME, weakest_sym)
        held_days = (
            (datetime.now(timezone.utc) - datetime.fromisoformat(bought_ts)).total_seconds() / 86400
            if bought_ts else settings.ROTATION_MIN_HOLD_DAYS + 1   # unknown entry -> don't block on age
        )
        if held_days >= settings.ROTATION_MIN_HOLD_DAYS:
            rotate_plan = (weakest_sym, weakest_score, best_new, best_score)
            break

if rotate_plan:
    weakest_sym, weakest_score, best_new, best_score = rotate_plan
    reason = (f"{weakest_sym} (score {weakest_score:+.0f}) is the weakest thing we hold, and "
              f"{best_new} (score {best_score:+.0f}) is waiting outside a full book — rotate.")
    pos = held[weakest_sym]
    a_w = analysis[weakest_sym]
    ref_w = price_now(weakest_sym)
    decision_id = record(run_id, weakest_sym, "SELL", reason, True, a_w, ref_w)
    print(f"  {weakest_sym}: ROTATE OUT -> {reason}")
    shares = float(pos.qty)
    ok, why = can_i_trade(trading, weakest_sym, shares, ref_w, "sell")
    if not ok:
        diary.log_trade(db, run_id, decision_id, weakest_sym, "sell", "blocked", shares=shares,
                        note="rotation; " + why, equity_before=equity_before, cash_before=cash_before)
        print(f"    bouncer blocked: {why}")
    else:
        if just_talking:
            diary.log_trade(db, run_id, decision_id, weakest_sym, "sell", "pretend", shares=shares,
                            fill_price=ref_w, note="rotation",
                            equity_before=equity_before, cash_before=cash_before)
            print(f"    WOULD sell {shares:g} {weakest_sym} (rotation)")
        else:
            status, fill, fqty, oid = do_sell(weakest_sym)
            diary.log_trade(db, run_id, decision_id, weakest_sym, "sell", status,
                            shares=fqty or shares, fill_price=fill, order_id=oid, note="rotation",
                            equity_before=equity_before, cash_before=cash_before)
            print(f"    {status} {(fqty or shares):g} {weakest_sym}"
                  + (f" @ ${fill:,.2f}" if fill else "") + " (rotation)")
        del held[weakest_sym]
        room = 1

print(f"\n--- scan found {len(shortlist)} candidates; room for {max(room,0)} more ---")
print(f"    shortlist: {', '.join(shortlist) or '(none)'}")
if cooling:
    print(f"    (cooling off, sold recently: {', '.join(sorted(cooling))})")

bought = 0
sector_counts = Counter(sector_of(s) for s in held)
for symbol in shortlist:
    a = analysis[symbol]
    ref = price_now(symbol)
    m3 = a.get("mom_63d")
    tag = "fresh crossover" if a["crossed_up"] else "trending up"
    reason = (f"{symbol} {tag}, 3-month momentum {m3:+.0f}%" if m3 is not None
              else f"{symbol} {tag}, +{a['move_5d_pct']}% in 5 days")
    reason += f" (RSI {a['rsi14']:.0f}, ATR {a['atr_pct']:.1f}%)." if a.get("rsi14") else "."

    if bought >= room:
        record(run_id, symbol, "WAIT", f"{reason} But no room (already hold {len(held)}).", False, a, ref)
        print(f"  {symbol}: skip (no room)")
        continue

    nv = news_verdict(symbol)
    if nv in ("avoid", "negative"):
        record(run_id, symbol, "WAIT",
               f"{reason} But overnight news is {nv} ({NEWS['stocks'][symbol]['reason']}) — skip.",
               False, a, ref)
        print(f"  {symbol}: skip (news: {nv})")
        continue

    sec = sector_of(symbol)
    if sec != "ETF" and sector_counts[sec] >= settings.MAX_STOCKS_PER_SECTOR:
        record(run_id, symbol, "WAIT",
               f"{reason} But already hold {sector_counts[sec]} {sec} stocks "
               f"(cap {settings.MAX_STOCKS_PER_SECTOR}).", False, a, ref)
        print(f"  {symbol}: skip (sector cap: {sec})")
        continue

    decision_id = record(run_id, symbol, "BUY", reason, False, a, ref)

    # volatility-scaled sizing: spend DOLLARS_PER_BUY x (target vol / this stock's
    # ATR%), clamped to [VOL_SIZING_MIN, VOL_SIZING_MAX], so every position
    # carries similar risk without starving a strong-but-jumpy momentum name.
    dollars = settings.DOLLARS_PER_BUY
    if getattr(settings, "USE_VOL_SIZING", False) and a.get("atr_pct"):
        _lo = getattr(settings, "VOL_SIZING_MIN", 0.5)
        _hi = getattr(settings, "VOL_SIZING_MAX", 1.5)
        scale = max(_lo, min(_hi, settings.TARGET_VOL_PCT / a["atr_pct"]))
        dollars = round(settings.DOLLARS_PER_BUY * scale, 2)
    approx_shares = dollars / ref          # fractional — priced in dollars, not whole shares


    ok, why = can_i_trade(trading, symbol, approx_shares, ref, "buy")
    if not ok:
        diary.log_trade(db, run_id, decision_id, symbol, "buy", "blocked", shares=approx_shares,
                        note=why, equity_before=equity_before, cash_before=cash_before)
        print(f"  {symbol}: bouncer blocked -> {why}")
        continue

    # SPY cash sleeve: not enough real cash for this buy -> sell some SPY first
    _cash = float(trading.get_account().cash)
    if _cash - 10 < dollars and sleeve_value() > 0:
        sleeve_trade("sell", min(sleeve_value(), dollars - _cash + 10 + 5),
                     f"fund {symbol} buy")

    if just_talking:
        diary.log_trade(db, run_id, decision_id, symbol, "buy", "pretend",
                        shares=round(approx_shares, 4), fill_price=ref,
                        equity_before=equity_before, cash_before=cash_before)
        print(f"  {symbol}: WOULD buy ~${dollars:,.0f} of {symbol} ({approx_shares:.3f} sh)")
        bought += 1
        sector_counts[sec] += 1
    else:
        status, fill, fqty, oid, note = place_buy(symbol, dollars, ref)
        diary.log_trade(db, run_id, decision_id, symbol, "buy", status, shares=fqty,
                        fill_price=fill, order_id=oid, note=note,
                        equity_before=equity_before, cash_before=cash_before)
        if status == "filled":
            print(f"  {symbol}: filled {fqty:g} @ ${fill:,.2f}  (~${fqty * fill:,.2f})  [{note}]")
            bought += 1
            sector_counts[sec] += 1
        else:
            print(f"  {symbol}: {status} — {note}")

# ---- 3. SPY cash sleeve: park idle cash (mirrors backtest.py) ------
_sv = sleeve_value()
if getattr(settings, "USE_SPY_CASH_SLEEVE", False) or _sv > 0:
    _cash = float(trading.get_account().cash)
    want = max(0.0, _cash + _sv - settings.SPY_SLEEVE_BUFFER)
    if not getattr(settings, "USE_SPY_CASH_SLEEVE", False):
        want, why = 0.0, "sleeve switched off"
    elif getattr(settings, "SPY_SLEEVE_RISK_OFF_EXIT", False) and not (market_ok and vol_ok):
        want, why = 0.0, "market-trend/volatility gate failed: sleeve to cash"
    else:
        why = f"park idle cash, keep ${settings.SPY_SLEEVE_BUFFER:,} in cash"
    delta = want - _sv
    print(f"\n--- SPY cash sleeve: holding ${_sv:,.0f}, target ${want:,.0f} ---")
    if want == 0 and _sv > 0:
        sleeve_trade("sell", None, why)
    elif abs(delta) >= settings.SPY_SLEEVE_MIN_TRADE:
        sleeve_trade("buy" if delta > 0 else "sell", abs(delta), why)
    else:
        print(f"  sleeve: within ${settings.SPY_SLEEVE_MIN_TRADE:,} of target, no trade")
if _sleeve_run is not None:
    diary.finish_run(db, _sleeve_run, None, None)

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
print(f"\nSaved to {os.path.basename(diary.DB_PATH)} as run #{run_id}.")
