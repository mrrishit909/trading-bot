"""
CRYPTO BACKTEST — has the coin strategy ever actually made money?

Same idea as backtest.py, for the crypto sleeve. Uses the EXACT signal math
from crypto_scanner.signals_from_series (2/3-day vs 6/10-day SMA crossover,
RSI14, 30-day momentum) and the EXACT entry/exit rules from step12_crypto.py
(hard stop, trailing stop, momentum-breakdown exit, SMA-reversal exit, re-buy
cooldown, "don't chase a blow-off top" guard) — day by day over real historical
daily bars for the whole crypto universe.

READ THIS BEFORE TRUSTING THE NUMBER:
  - Executes at each day's CLOSING price with a slippage haircut
    (settings.CRYPTO_SLIPPAGE_PCT, 0.15% — wider than stocks). Real 24/7 fills
    would differ.
  - No look-ahead: every signal on day t uses bars up to day t's close only.
  - Crypto only. The benchmark is buy-and-hold BTC (crypto's "index").
  - Newer coins simply don't trade until they have enough history.
  - ONE historical path. Crypto's last 2 years were unusually strong; that is
    not a promise about the next 2.

Run it:
    ./venv/bin/python backtest_crypto.py                (last ~2 years)
    ./venv/bin/python backtest_crypto.py --years 1
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from bisect import bisect_right

from dotenv import load_dotenv
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

import settings
from crypto_scanner import signals_from_series, rank_buys

load_dotenv()
cdc = CryptoHistoricalDataClient()

YEARS = float(sys.argv[sys.argv.index("--years") + 1]) if "--years" in sys.argv else 2.0
WARMUP_DAYS = 40          # > MOM_DAYS(30)+1, enough for RSI14 and the 20-day recent-high
HERE = os.path.dirname(os.path.abspath(__file__))
# what the sleeve can actually deploy: every slot filled at the standard size
START_CASH = float(settings.MAX_CRYPTO_HELD * settings.CRYPTO_DOLLARS_PER_BUY)


def fetch_history(symbols, years):
    start = datetime.now(timezone.utc) - timedelta(days=int(years * 365) + WARMUP_DAYS + 10)
    print(f"Fetching {len(symbols)} coins, ~{years} years of daily bars...")
    bars = cdc.get_crypto_bars(CryptoBarsRequest(
        symbol_or_symbols=list(symbols), timeframe=TimeFrame.Day, start=start,
    )).data
    out = {}
    for sym in symbols:
        rows = sorted(bars.get(sym, []), key=lambda b: b.timestamp)
        out[sym] = {
            "dates": [b.timestamp.date() for b in rows],
            "closes": [b.close for b in rows],
        }
    return out


def window_signals(hist, sym, date):
    d = hist[sym]
    idx = bisect_right(d["dates"], date)
    if idx == 0:
        return {"enough_data": False}
    lo = max(0, idx - (WARMUP_DAYS + 25))
    return signals_from_series(d["closes"][lo:idx])


def price_on(hist, sym, date):
    d = hist[sym]
    idx = bisect_right(d["dates"], date)
    return d["closes"][idx - 1] if idx else None


def run():
    universe = list(settings.CRYPTO_UNIVERSE)
    symbols = sorted(set(universe) | {"BTC/USD"})
    hist = fetch_history(symbols, YEARS)

    # crypto trades 24/7 — use the union of all coins' dates as the calendar
    all_dates = sorted({d for s in symbols for d in hist[s]["dates"]})
    if len(all_dates) < WARMUP_DAYS + 30:
        print("Not enough crypto history for this --years. Try a smaller value.")
        return

    slip = settings.CRYPTO_SLIPPAGE_PCT / 100
    cash = START_CASH
    positions = {}       # sym -> {qty, entry_price, entry_date, peak}
    cooldown = {}
    closed_trades = []
    equity_curve = []

    sim_days = all_dates[WARMUP_DAYS:]
    print(f"Simulating {len(sim_days)} days, {sim_days[0]} -> {sim_days[-1]} ...")

    brk = settings.CRYPTO_MOMENTUM_BREAKDOWN_PCT
    trail = settings.CRYPTO_TRAILING_STOP_PCT
    hard = settings.CRYPTO_STOP_LOSS_PCT

    for today in sim_days:
        # ---- SELL pass (mirrors step12_crypto.py) ----
        for sym in list(positions):
            price = price_on(hist, sym, today)
            if price is None:
                continue
            sig = window_signals(hist, sym, today)
            pos = positions[sym]
            pos["peak"] = max(pos["peak"], price)
            loss_pct = (price / pos["entry_price"] - 1) * 100
            dd_pct = (price / pos["peak"] - 1) * 100

            sell = (loss_pct <= -hard
                    or (loss_pct > 0 and dd_pct <= -trail)
                    or (sig.get("mom_30d") is not None and sig["mom_30d"] <= -brk)
                    or not sig.get("enough_data") or sig.get("sell_signal"))

            if sell:
                sell_px = price * (1 - slip)
                cost = pos["qty"] * pos["entry_price"] * (1 + slip)
                proceeds = pos["qty"] * sell_px
                cash += proceeds
                closed_trades.append({
                    "symbol": sym, "entry_date": str(pos["entry_date"]), "exit_date": str(today),
                    "entry_price": round(pos["entry_price"], 4), "exit_price": round(price, 4),
                    "ret_pct": round((proceeds / cost - 1) * 100, 2),
                    "pnl": round(proceeds - cost, 2),
                    "hold_days": (today - pos["entry_date"]).days,
                })
                cooldown[sym] = today
                del positions[sym]

        # ---- BUY pass ----
        room = settings.MAX_CRYPTO_HELD - len(positions)
        if room > 0:
            cooling = {s for s, dt in cooldown.items()
                       if (today - dt).days < settings.REBUY_COOLDOWN_DAYS}
            analysis = {}
            for sym in universe:
                if sym in positions or sym in cooling:
                    continue
                sig = window_signals(hist, sym, today)
                if sig.get("enough_data"):
                    analysis[sym] = sig
            shortlist = rank_buys(analysis)
            bought = 0
            for sym in shortlist:
                if bought >= room:
                    break
                sig = analysis[sym]
                if sig["move_1d_pct"] > settings.CRYPTO_CHASE_LIMIT_PCT:
                    continue
                price = price_on(hist, sym, today)
                if not price:
                    continue
                dollars = min(settings.CRYPTO_DOLLARS_PER_BUY, max(cash - 1, 0))
                if dollars < 5:
                    continue
                buy_px = price * (1 + slip)
                positions[sym] = {"qty": dollars / buy_px, "entry_price": price,
                                  "entry_date": today, "peak": price}
                cash -= dollars
                bought += 1

        equity = cash + sum(p["qty"] * (price_on(hist, s, today) or p["entry_price"])
                            for s, p in positions.items())
        equity_curve.append((today, equity))

    report(hist, equity_curve, closed_trades)


def report(hist, equity_curve, closed_trades):
    vals = [v for _, v in equity_curve]
    dates = [d for d, _ in equity_curve]
    final = vals[-1]
    total_ret = (final / START_CASH - 1) * 100
    years_run = (dates[-1] - dates[0]).days / 365.25
    cagr = ((final / START_CASH) ** (1 / years_run) - 1) * 100 if years_run > 0 and final > 0 else 0.0

    peak, max_dd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        max_dd = min(max_dd, (v / peak - 1) * 100)

    btc_start = price_on(hist, "BTC/USD", dates[0])
    btc_end = price_on(hist, "BTC/USD", dates[-1])
    btc_ret = (btc_end / btc_start - 1) * 100

    n = len(closed_trades)
    wins = sum(1 for t in closed_trades if t["pnl"] > 0)
    avg_ret = sum(t["ret_pct"] for t in closed_trades) / n if n else 0.0
    avg_hold = sum(t["hold_days"] for t in closed_trades) / n if n else 0.0
    best = max(closed_trades, key=lambda t: t["ret_pct"], default=None)
    worst = min(closed_trades, key=lambda t: t["ret_pct"], default=None)

    print("\n" + "=" * 66)
    print(f"CRYPTO BACKTEST  {dates[0]} -> {dates[-1]}  ({years_run:.1f} years)")
    print("=" * 66)
    print(f"  start:            ${START_CASH:,.2f}   (MAX_CRYPTO_HELD x CRYPTO_DOLLARS_PER_BUY)")
    print(f"  end:              ${final:,.2f}")
    print(f"  total return:     {total_ret:+.1f}%")
    print(f"  CAGR:             {cagr:+.1f}%/yr")
    print(f"  max drawdown:     {max_dd:.1f}%")
    print(f"  buy & hold BTC, same period: {btc_ret:+.1f}%   "
          f"({'BEAT' if total_ret > btc_ret else 'LOST TO'} it by {abs(total_ret-btc_ret):.1f} points)")
    print()
    print(f"  completed trades:  {n}")
    if n:
        print(f"  win rate:          {100*wins/n:.0f}%  ({wins} won / {n-wins} lost)")
        print(f"  avg trade:         {avg_ret:+.2f}%   avg hold: {avg_hold:.0f} days")
        print(f"  best / worst:      {best['symbol']} {best['ret_pct']:+.1f}%  /  "
              f"{worst['symbol']} {worst['ret_pct']:+.1f}%")
    print("=" * 66)
    print("Closing-price fills, one historical path. Crypto's last 2 years were")
    print("unusually strong — treat this as 'plausible or not', not a forecast.")

    os.makedirs(os.path.join(HERE, "research"), exist_ok=True)
    out_path = os.path.join(HERE, "research", f"backtest_crypto_{dates[0]}_{dates[-1]}.md")
    with open(out_path, "w") as fh:
        fh.write(f"# Crypto backtest — {dates[0]} to {dates[-1]} ({years_run:.1f} years)\n\n")
        fh.write(f"- Start ${START_CASH:,.0f} -> End ${final:,.2f}  ({total_ret:+.1f}%, {cagr:+.1f}%/yr)\n")
        fh.write(f"- Max drawdown: {max_dd:.1f}%\n")
        fh.write(f"- Buy & hold BTC, same period: {btc_ret:+.1f}%\n")
        if n:
            fh.write(f"- {n} completed trades, {100*wins/n:.0f}% win rate, avg {avg_ret:+.2f}%, "
                     f"avg hold {avg_hold:.0f}d\n\n")
        else:
            fh.write("- No completed trades.\n\n")
        fh.write("Same signal math as live (`crypto_scanner.signals_from_series`) and same "
                 "exit rules as `step12_crypto.py`. Closing-price fills with a "
                 f"{settings.CRYPTO_SLIPPAGE_PCT}% slippage haircut on each leg. One path.\n\n")
        fh.write("<details><summary>closed trades</summary>\n\n```json\n")
        fh.write(json.dumps(closed_trades, indent=2))
        fh.write("\n```\n\n</details>\n")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    run()
