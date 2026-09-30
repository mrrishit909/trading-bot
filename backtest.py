"""
BACKTEST — did this strategy actually make money over the last few years?

Simulates the CURRENT stock strategy — the exact same signal math from
scanner.py (SMA crossover, RSI, ATR%, 3-/6-month momentum) and the exact same
entry/exit rules as step10_scan_and_trade.py (market filter, momentum rank,
ATR stop, trailing stop, momentum-breakdown exit, re-buy cooldown, sector
cap, volatility-scaled sizing) — day by day over REAL historical prices for
the whole 300-stock universe. Answers "does this approach work" in a couple
of minutes instead of waiting weeks for live paper data.

READ THIS BEFORE TRUSTING THE NUMBER:
  - Executes at each day's CLOSING price. A slippage haircut is applied (see
    settings.STOCK_SLIPPAGE_PCT) but the TIMING is optimistic — a live bot
    running intraday would get different, unknowable fills.
  - No look-ahead: every signal on day t is computed from bars up to and
    including day t's close only — never a peek at day t+1.
  - Stocks only. Options and crypto are not simulated here.
  - The pre-market news filter (news_scan.py) is NOT replayed — there's no
    historical news-sentiment feed. The backtest is the mechanical strategy
    without the news overlay.
  - This is ONE historical path. A strategy that worked the last few years
    can still fail the next few — and several of these exact rules were
    added after watching a few days of live results, which is a real
    curve-fitting risk. Treat this as "plausible or not", not a guarantee.

Run it:
    ./venv/bin/python backtest.py                (last ~2.5 years)
    ./venv/bin/python backtest.py --years 1.5
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from collections import Counter
from bisect import bisect_right

from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment

import settings
from scanner import signals_from_series, rank_buys, momentum_score, MIN_PRICE
from sectors import sector_of

load_dotenv()
K, S = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
data = StockHistoricalDataClient(K, S)

YEARS = float(sys.argv[sys.argv.index("--years") + 1]) if "--years" in sys.argv else 2.5
START_CASH = 100_000.0
WARMUP_DAYS = 140     # > MOM_LONG_DAYS(126) so every signal is available once trading starts
HERE = os.path.dirname(os.path.abspath(__file__))


def fetch_history(symbols, years):
    start = datetime.now(timezone.utc) - timedelta(days=int(years * 365) + 60)
    print(f"Fetching {len(symbols)} symbols, ~{years} years of daily bars (adjusted)...")
    bars = data.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=start,
        adjustment=Adjustment.ALL,
    )).data
    out = {}
    for sym in symbols:
        rows = bars.get(sym, [])
        out[sym] = {
            "dates": [b.timestamp.date() for b in rows],
            "closes": [b.close for b in rows],
            "highs": [b.high for b in rows],
            "lows": [b.low for b in rows],
        }
    return out


def window_signals(hist, sym, date):
    """Every signal for `sym` as of `date` — uses only bars up to and
    including that date, via the SAME math scanner.py uses live."""
    d = hist[sym]
    idx = bisect_right(d["dates"], date)
    if idx == 0:
        return {"enough_data": False}
    lo = max(0, idx - WARMUP_DAYS)
    return signals_from_series(d["closes"][lo:idx], d["highs"][lo:idx], d["lows"][lo:idx])


def price_on(hist, sym, date):
    d = hist[sym]
    idx = bisect_right(d["dates"], date)
    return d["closes"][idx - 1] if idx else None


def run():
    universe = list(settings.ALLOWED_STOCKS)
    symbols = sorted(set(universe) | {"SPY"})
    hist = fetch_history(symbols, YEARS)

    calendar = hist["SPY"]["dates"]
    if len(calendar) < WARMUP_DAYS + 20:
        print("Not enough SPY history for this --years. Try a smaller value.")
        return

    slip = settings.STOCK_SLIPPAGE_PCT / 100
    cash = START_CASH
    spy_qty = 0.0        # SPY cash sleeve (mirrors step10): idle cash parked in SPY
    sleeve_on = getattr(settings, "USE_SPY_CASH_SLEEVE", False)
    positions = {}       # sym -> {qty, entry_price, entry_date}
    cooldown = {}        # sym -> date last sold
    closed_trades = []
    equity_curve = []    # (date, equity)

    sim_days = calendar[WARMUP_DAYS:]
    print(f"Simulating {len(sim_days)} trading days, {calendar[WARMUP_DAYS]} -> {calendar[-1]} ...")

    for i, today in enumerate(calendar):
        if i < WARMUP_DAYS:
            continue

        spy_sig = window_signals(hist, "SPY", today)
        _spy_mom = spy_sig.get("mom_63d")
        market_ok = ((not settings.USE_MARKET_FILTER) or (not spy_sig.get("enough_data"))
                     or _spy_mom is None
                     or _spy_mom >= settings.MARKET_TREND_MIN_MOM63)
        vol_ok = ((not settings.USE_VOLATILITY_FILTER) or (not spy_sig.get("atr_pct"))
                 or spy_sig["atr_pct"] <= settings.MAX_MARKET_ATR_PCT)
        market_ok = market_ok and vol_ok

        # ---- SELL pass (mirrors step10_scan_and_trade.py) ----
        for sym in list(positions):
            price = price_on(hist, sym, today)
            if price is None:
                continue
            sig = window_signals(hist, sym, today)
            pos = positions[sym]
            loss_pct = (price / pos["entry_price"] - 1) * 100
            peak = sig.get("recent_high") or price
            dd_pct = (price / peak - 1) * 100 if peak else 0.0

            stop_pct = settings.STOCK_STOP_LOSS_PCT
            if settings.USE_ATR_STOP and sig.get("atr_pct"):
                stop_pct = min(settings.STOCK_STOP_LOSS_PCT,
                               max(4.0, settings.STOCK_STOP_ATR_MULT * sig["atr_pct"]))

            sell = (loss_pct <= -stop_pct
                    or (loss_pct > 0 and dd_pct <= -settings.TRAILING_STOP_PCT)
                    or (sig.get("mom_63d") is not None
                        and sig["mom_63d"] <= -settings.MOMENTUM_BREAKDOWN_PCT)
                    or not sig.get("enough_data") or sig.get("sell_signal"))

            scale_out = (not sell
                         and getattr(settings, "SCALE_OUT_ENABLED", False)
                         and not pos.get("scaled")
                         and loss_pct >= settings.SCALE_OUT_GAIN_PCT)

            if scale_out:
                frac = settings.SCALE_OUT_FRACTION
                sell_px = price * (1 - slip)
                qty_out = pos["qty"] * frac
                cost_out = qty_out * pos["entry_price"] * (1 + slip)
                proceeds = qty_out * sell_px
                cash += proceeds
                closed_trades.append({
                    "symbol": sym, "entry_date": str(pos["entry_date"]), "exit_date": str(today),
                    "entry_price": round(pos["entry_price"], 2), "exit_price": round(price, 2),
                    "ret_pct": round((proceeds / cost_out - 1) * 100, 2),
                    "pnl": round(proceeds - cost_out, 2),
                    "hold_days": (today - pos["entry_date"]).days, "note": "scale-out",
                })
                pos["qty"] -= qty_out
                pos["scaled"] = True

            if sell:
                sell_px = price * (1 - slip)
                buy_cost_basis = pos["qty"] * pos["entry_price"] * (1 + slip)
                proceeds = pos["qty"] * sell_px
                cash += proceeds
                closed_trades.append({
                    "symbol": sym, "entry_date": str(pos["entry_date"]), "exit_date": str(today),
                    "entry_price": round(pos["entry_price"], 2), "exit_price": round(price, 2),
                    "ret_pct": round((proceeds / buy_cost_basis - 1) * 100, 2),
                    "pnl": round(proceeds - buy_cost_basis, 2),
                    "hold_days": (today - pos["entry_date"]).days,
                })
                cooldown[sym] = today
                del positions[sym]

        # ---- BUY pass ----
        room = settings.MAX_STOCKS_HELD - len(positions)
        if market_ok:
            cooling = {s for s, d in cooldown.items() if (today - d).days < settings.REBUY_COOLDOWN_DAYS}
            analysis = {}
            for sym in universe:
                if sym in positions or sym in cooling:
                    continue
                sig = window_signals(hist, sym, today)
                if sig.get("enough_data"):
                    analysis[sym] = sig
            shortlist = rank_buys(analysis, exclude={"SPY"})[:settings.SHORTLIST_SIZE]

            # rank-based rotation (mirrors step10_scan_and_trade.py): book is full,
            # but the best waiting candidate clearly outranks the weakest thing we
            # hold -> sell the weakest (any sector — see step10 for why this is
            # deliberately not sector-matched) and free one slot for the normal
            # BUY loop below to fill (it already enforces the sector cap).
            if room <= 0 and getattr(settings, "USE_RANK_ROTATION", False) and shortlist and positions:
                best_new = shortlist[0]
                best_score = momentum_score(analysis[best_new])
                pool_signals = {s: window_signals(hist, s, today) for s in positions}
                scored = sorted(
                    ((momentum_score(pool_signals[s]), s) for s in positions if pool_signals[s].get("enough_data")),
                    key=lambda t: t[0],
                )
                for w_score, w_sym in scored:
                    if best_score - w_score < settings.ROTATION_MARGIN_PTS:
                        break
                    if (today - positions[w_sym]["entry_date"]).days < settings.ROTATION_MIN_HOLD_DAYS:
                        continue
                    price = price_on(hist, w_sym, today)
                    if price is None:
                        continue
                    sell_px = price * (1 - slip)
                    cost = positions[w_sym]["qty"] * positions[w_sym]["entry_price"] * (1 + slip)
                    proceeds = positions[w_sym]["qty"] * sell_px
                    cash += proceeds
                    closed_trades.append({
                        "symbol": w_sym, "entry_date": str(positions[w_sym]["entry_date"]),
                        "exit_date": str(today), "entry_price": round(positions[w_sym]["entry_price"], 2),
                        "exit_price": round(price, 2),
                        "ret_pct": round((proceeds / cost - 1) * 100, 2), "pnl": round(proceeds - cost, 2),
                        "hold_days": (today - positions[w_sym]["entry_date"]).days, "note": "rotation",
                    })
                    cooldown[w_sym] = today
                    del positions[w_sym]
                    room = 1
                    break

        if market_ok and room > 0:
            sector_counts = Counter(sector_of(s) for s in positions)
            bought = 0
            for sym in shortlist:
                if bought >= room:
                    break
                sec = sector_of(sym)
                if sec != "ETF" and sector_counts[sec] >= settings.MAX_STOCKS_PER_SECTOR:
                    continue
                price = price_on(hist, sym, today)
                if not price or price < MIN_PRICE:
                    continue
                sig = analysis[sym]
                dollars = settings.DOLLARS_PER_BUY
                if settings.USE_VOL_SIZING and sig.get("atr_pct"):
                    _lo = getattr(settings, "VOL_SIZING_MIN", 0.5)
                    _hi = getattr(settings, "VOL_SIZING_MAX", 1.5)
                    scale = max(_lo, min(_hi, settings.TARGET_VOL_PCT / sig["atr_pct"]))
                    dollars = settings.DOLLARS_PER_BUY * scale
                if sleeve_on and spy_qty > 0 and dollars > cash - 10:   # fund the buy from the sleeve
                    spy_px = price_on(hist, "SPY", today)
                    q = min(spy_qty, (dollars - cash + 10) / (spy_px * (1 - slip)))
                    cash += q * spy_px * (1 - slip)
                    spy_qty -= q
                dollars = min(dollars, max(cash - 10, 0))
                if dollars < 20:
                    continue
                buy_px = price * (1 + slip)
                positions[sym] = {"qty": dollars / buy_px, "entry_price": price,
                                  "entry_date": today, "scaled": False}
                cash -= dollars
                sector_counts[sec] += 1
                bought += 1

        spy_px = price_on(hist, "SPY", today)
        if sleeve_on or spy_qty > 0:
            spy_val = spy_qty * spy_px
            want = max(0.0, cash + spy_val - settings.SPY_SLEEVE_BUFFER)
            if getattr(settings, "SPY_SLEEVE_RISK_OFF_EXIT", False) and not market_ok:
                want = 0.0
            delta = want - spy_val
            if abs(delta) >= settings.SPY_SLEEVE_MIN_TRADE or (want == 0 and spy_qty > 0):
                if delta > 0:
                    spy_qty += delta / (spy_px * (1 + slip))
                    cash -= delta
                else:
                    q = min(spy_qty, -delta / spy_px)
                    cash += q * spy_px * (1 - slip)
                    spy_qty -= q
        equity = cash + spy_qty * spy_px + sum(pos["qty"] * (price_on(hist, s, today) or pos["entry_price"])
                                               for s, pos in positions.items())
        equity_curve.append((today, equity))

    report(hist, equity_curve, closed_trades, calendar)


def report(hist, equity_curve, closed_trades, calendar):
    vals = [v for _, v in equity_curve]
    dates = [d for d, _ in equity_curve]
    final = vals[-1]
    total_ret = (final / START_CASH - 1) * 100
    years_run = (dates[-1] - dates[0]).days / 365.25
    cagr = ((final / START_CASH) ** (1 / years_run) - 1) * 100 if years_run > 0 else 0.0

    peak = vals[0]
    max_dd = 0.0
    for v in vals:
        peak = max(peak, v)
        max_dd = min(max_dd, (v / peak - 1) * 100)

    spy_start = price_on(hist, "SPY", dates[0])
    spy_end = price_on(hist, "SPY", dates[-1])
    spy_ret = (spy_end / spy_start - 1) * 100

    n = len(closed_trades)
    wins = sum(1 for t in closed_trades if t["pnl"] > 0)
    avg_ret = sum(t["ret_pct"] for t in closed_trades) / n if n else 0.0
    avg_hold = sum(t["hold_days"] for t in closed_trades) / n if n else 0.0
    best = max(closed_trades, key=lambda t: t["ret_pct"], default=None)
    worst = min(closed_trades, key=lambda t: t["ret_pct"], default=None)

    print("\n" + "=" * 66)
    print(f"BACKTEST  {dates[0]} -> {dates[-1]}  ({years_run:.1f} years, {len(dates)} sim days)")
    print("=" * 66)
    print(f"  start:            ${START_CASH:,.2f}")
    print(f"  end:              ${final:,.2f}")
    print(f"  total return:     {total_ret:+.1f}%")
    print(f"  CAGR:             {cagr:+.1f}%/yr")
    print(f"  max drawdown:     {max_dd:.1f}%")
    print(f"  same period, buy & hold SPY: {spy_ret:+.1f}%   ({'BEAT' if total_ret>spy_ret else 'LOST TO'} it "
          f"by {abs(total_ret-spy_ret):.1f} points)")
    print()
    print(f"  completed trades:  {n}")
    if n:
        print(f"  win rate:          {100*wins/n:.0f}%  ({wins} won / {n-wins} lost)")
        print(f"  avg trade:         {avg_ret:+.2f}%   avg hold: {avg_hold:.0f} days")
        print(f"  best / worst:      {best['symbol']} {best['ret_pct']:+.1f}%  /  "
              f"{worst['symbol']} {worst['ret_pct']:+.1f}%")
    print("=" * 66)
    print("Reminder: closing-price fills, one historical path, and some rules here")
    print("were tuned after watching live results — treat this as a plausibility")
    print("check, not proof it'll do this again.")

    os.makedirs(os.path.join(HERE, "research"), exist_ok=True)
    out_path = os.path.join(HERE, "research", f"backtest_{dates[0]}_{dates[-1]}.md")
    with open(out_path, "w") as fh:
        fh.write(f"# Backtest — {dates[0]} to {dates[-1]} ({years_run:.1f} years)\n\n")
        fh.write(f"- Start: ${START_CASH:,.2f}  ->  End: ${final:,.2f}  ({total_ret:+.1f}%, "
                 f"{cagr:+.1f}%/yr CAGR)\n")
        fh.write(f"- Max drawdown: {max_dd:.1f}%\n")
        fh.write(f"- SPY buy & hold, same period: {spy_ret:+.1f}%\n")
        fh.write(f"- Completed trades: {n}, win rate {100*wins/n:.0f}%, avg {avg_ret:+.2f}%, "
                 f"avg hold {avg_hold:.0f}d\n\n" if n else "- No completed trades.\n\n")
        fh.write("Executes at closing prices with a slippage haircut applied; timing is "
                 "still optimistic vs. real intraday fills. Stocks only (no options/crypto). "
                 "One historical path — not a guarantee of future results, and some of these "
                 "exact rules were tuned after watching a few days of live paper trading, "
                 "which is a real curve-fitting risk.\n\n")
        fh.write("<details><summary>closed trades</summary>\n\n```json\n"
                 + json.dumps(closed_trades, indent=2, default=str) + "\n```\n</details>\n")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    run()
