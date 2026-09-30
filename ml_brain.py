"""
ML BRAIN (experiment): a neural network with an exact number of knobs (--knobs, default 10,000).

The ~58 knobs in settings.py are ones WE pick by hand.
These the robot tunes BY ITSELF by studying old prices:

  - Give it ~60 clues about a stock on a given day (momentum, RSI, volume,
    volatility, the whole market's mood, its sector, how it ranks vs every
    other stock, earnings-like jumps, its last 20 daily moves)
  - Ask: "will this stock beat the typical stock over the next 5 days?"
  - It guesses, checks the real answer, nudges its knobs, repeats.

Then it takes a PRETEND trading exam on months it never studied: every
5 days, buy its top 10 picks, pay slippage, sell 5 days later. Compared
against simply holding SPY.

ADVISORY ONLY. This file never places orders and nothing live imports it.

  ./venv/bin/python ml_brain.py [--knobs N] [--years N]  # train, take the exam, show today's picks
  ./venv/bin/python ml_brain.py --log [--knobs N]        # write today's top picks to diary.db (no trades)
  ./venv/bin/python ml_brain.py --selftest               # quick math check, no internet
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

STRATEGY_NAME = "ml_brain_v1"
HORIZON = 5          # predict 5 trading days ahead
TRAIN_FRAC = 0.7     # first 70% of dates = study, last 30% = exam
VAL_FRAC = 0.15      # last 15% of the study dates = pop quizzes, to pick the best epoch
PICKS = 10           # exam: how many stocks it buys each round
MAX_EPOCHS = 8
BATCH = 1024
SECTORS = ['Communication Services', 'Consumer Discretionary', 'Consumer Staples', 'ETF',
           'Energy', 'Financials', 'Health Care', 'Industrials', 'Information Technology',
           'Materials', 'Real Estate', 'Utilities', 'Other']


# ---------- the clues ----------

def fetch_panels(symbols, years):
    """Daily adjusted bars as date x symbol tables: close, high, low, volume."""
    from dotenv import load_dotenv
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import Adjustment

    load_dotenv()
    client = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))
    start = datetime.now(timezone.utc) - timedelta(days=int(years * 365) + 200)
    print(f"Fetching {len(symbols)} symbols, ~{years} years of daily bars...")
    df = client.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=start,
        adjustment=Adjustment.ALL)).df.reset_index()
    df["date"] = df["timestamp"].dt.date
    return {k: df.pivot(index="date", columns="symbol", values=k)
            for k in ("open", "close", "high", "low", "volume")}


def build_features(p):
    """Returns (features dict name -> date x symbol table, label table, 5-day forward return table)."""
    from sectors import sector_of
    c, h, l, v = p["close"], p["high"], p["low"], p["volume"]
    r = c.pct_change(fill_method=None)
    spy = c["SPY"]
    spy_r = r["SPY"]
    f = {}

    # momentum: how much it moved over different windows
    for n in (1, 5, 10, 21, 63, 126):
        f[f"ret_{n}"] = c / c.shift(n) - 1
    # RSI 14 (Wilder)
    up, down = r.clip(lower=0), -r.clip(upper=0)
    f["rsi14"] = 100 - 100 / (1 + up.ewm(alpha=1 / 14).mean() / down.ewm(alpha=1 / 14).mean())
    # volatility: ATR% and daily-move spread
    prev = c.shift(1)
    tr = np.maximum(h - l, np.maximum((h - prev).abs(), (l - prev).abs()))
    f["atr_pct"] = tr.rolling(14).mean() / c
    f["vol_21"] = r.rolling(21).std()
    # trend: distance from moving averages
    for n in (5, 20, 50, 100):
        f[f"vs_sma{n}"] = c / c.rolling(n).mean() - 1
    f["sma5_above_20"] = (c.rolling(5).mean() > c.rolling(20).mean()).astype(float)
    # where it sits in its recent range
    f["pos_in_63d_range"] = (c - l.rolling(63).min()) / (h.rolling(63).max() - l.rolling(63).min())
    f["drawdown_126d"] = c / h.rolling(126).max() - 1
    # volume: is trading heating up? how big/liquid is it?
    f["vol_ratio_5_63"] = v.rolling(5).mean() / v.rolling(63).mean()
    f["log_dollar_vol"] = np.log1p((c * v).rolling(21).mean())
    # the whole market's mood (SPY), same value for every stock that day
    like = lambda s: pd.DataFrame(np.repeat(s.values[:, None], c.shape[1], 1), index=c.index, columns=c.columns)
    for n in (5, 21, 63):
        f[f"spy_ret_{n}"] = like(spy / spy.shift(n) - 1)
    f["spy_atr_pct"] = f["atr_pct"]["SPY"].pipe(like)
    f["spy_above_sma50"] = like((spy > spy.rolling(50).mean()).astype(float))
    # stock vs market
    f["rel_strength_63"] = f["ret_63"].sub(f["ret_63"]["SPY"], axis=0)
    cov = r.mul(spy_r, axis=0).rolling(63).mean() - r.rolling(63).mean().mul(spy_r.rolling(63).mean(), axis=0)
    f["beta_63"] = cov.div(spy_r.rolling(63).var(ddof=0), axis=0)
    # rank vs every other stock that day (0 = worst, 1 = best)
    for k in ("ret_21", "ret_63", "ret_126", "vol_21"):
        f[f"rank_{k}"] = f[k].rank(axis=1, pct=True)
    # sector: which one (one-hot) + is the whole sector hot right now?
    sec = pd.Series({s: sector_of(s) for s in c.columns})
    for s in SECTORS:
        f[f"sector_{s}"] = like(pd.Series(1.0, index=c.index)) * (sec == s).astype(float)
    sec_mean = f["ret_21"].T.groupby(sec).transform("mean").T
    f["sector_ret21_vs_all"] = sec_mean.sub(f["ret_21"].mean(axis=1), axis=0)
    # earnings-like events (no free earnings calendar goes back years, so spot them):
    # a big overnight gap on 3x normal volume. Companies report ~every 63 trading days.
    gap = p["open"] / prev - 1
    event = (gap.abs() > 2.5 * f["vol_21"]) & (v > 3 * v.rolling(63).mean())
    idx = pd.DataFrame(np.arange(len(c))[:, None].repeat(c.shape[1], 1), index=c.index, columns=c.columns)
    since = (idx - idx.where(event).ffill()).clip(upper=126)
    f["days_since_event"] = since.fillna(126)
    f["est_days_to_next_event"] = (63 - since).clip(lower=-63).fillna(0)
    f["last_event_move"] = r.where(event).ffill().fillna(0)   # stocks tend to drift after a surprise
    f["last_event_gap"] = gap.where(event).ffill().fillna(0)
    # raw pattern: last 20 daily moves, scaled by the stock's own volatility
    for i in range(20):
        f[f"move_{i}"] = r.shift(i) / f["vol_21"]

    fwd = c.shift(-HORIZON) / c - 1
    label = fwd.gt(fwd.median(axis=1), axis=0).astype(float).where(fwd.notna())
    return f, label, fwd


def stack(f, label, fwd):
    """Tables -> one row per (day, stock)."""
    names = list(f)
    X = np.stack([f[n].values for n in names], axis=-1)            # date x symbol x feature
    D, S, F = X.shape
    dates = np.repeat(np.array(f[names[0]].index), S)
    syms = np.tile(np.array(f[names[0]].columns), D)
    X = X.reshape(D * S, F)
    y, fw = label.values.ravel(), fwd.values.ravel()
    ok = np.isfinite(X).all(1)
    return names, X[ok].astype(np.float32), y[ok], fw[ok], dates[ok], syms[ok]


# ---------- the brain ----------

def layer_sizes(n_in, knobs):
    """Two hidden layers, first ~2x the second, total as close to `knobs` as possible.
    total = H1*(n_in+1) + H1*H2 + H2 + H2 + 1"""
    best = None
    for h2 in range(1, knobs // (n_in + 3) + 1):
        for h1 in {(knobs - 1 - 2 * h2) // (n_in + 1 + h2), (knobs - 1 - 2 * h2) // (n_in + 1 + h2) + 1}:
            if h1 > 0:
                total = h1 * (n_in + 1 + h2) + 2 * h2 + 1
                key = (abs(total - knobs) > knobs * 0.001, abs(h1 - 2 * h2), abs(total - knobs))
                if best is None or key < best[0]:
                    best = (key, h1, h2)
    return best[1:]


def new_model(n_in, knobs, rng):
    h1, h2 = layer_sizes(n_in, knobs)
    he = lambda a, b: rng.normal(0, np.sqrt(2 / a), (a, b)).astype(np.float32)
    return {"W1": he(n_in, h1), "b1": np.zeros(h1, np.float32),
            "W2": he(h1, h2), "b2": np.zeros(h2, np.float32),
            "W3": he(h2, 1) * 0.1, "b3": np.zeros(1, np.float32)}


def count_knobs(m):
    return sum(v.size for v in m.values())


def forward(m, X):
    a1 = np.maximum(X @ m["W1"] + m["b1"], 0)
    a2 = np.maximum(a1 @ m["W2"] + m["b2"], 0)
    return a1, a2, 1 / (1 + np.exp(-(a2 @ m["W3"] + m["b3"]).ravel()))


def predict(m, X):
    return np.concatenate([forward(m, X[i:i + 8192])[2] for i in range(0, len(X), 8192)])


def logloss(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def train(m, X, y, Xv=None, yv=None, epochs=MAX_EPOCHS, lr=3e-4, l2=1e-5, rng=None, log=print):
    """Mini-batch Adam. If a quiz set is given, keeps the knobs from the best quiz epoch."""
    rng = rng or np.random.default_rng(0)
    state = {k: (np.zeros_like(v), np.zeros_like(v)) for k, v in m.items()}
    best, best_loss, t = None, np.inf, 0
    for ep in range(1, epochs + 1):
        t0 = time.time()
        order = rng.permutation(len(X))
        for i in range(0, len(X), BATCH):
            idx = order[i:i + BATCH]
            xb, yb = X[idx], y[idx].astype(np.float32)
            a1, a2, p = forward(m, xb)
            d3 = ((p - yb) / len(yb))[:, None].astype(np.float32)
            d2 = (d3 @ m["W3"].T) * (a2 > 0)
            d1 = (d2 @ m["W2"].T) * (a1 > 0)
            grads = {"W3": a2.T @ d3, "b3": d3.sum(0), "W2": a1.T @ d2 + l2 * m["W2"],
                     "b2": d2.sum(0), "W1": xb.T @ d1 + l2 * m["W1"], "b1": d1.sum(0)}
            t += 1
            for k, g in grads.items():
                a, b = state[k]
                a *= 0.9; a += 0.1 * g
                b *= 0.999; b += 0.001 * g * g
                m[k] -= lr * (a / (1 - 0.9 ** t)) / (np.sqrt(b / (1 - 0.999 ** t)) + 1e-8)
        msg = f"  epoch {ep}: study loss {logloss(predict(m, X[:50000]), y[:50000]):.4f}"
        if Xv is not None:
            vl = logloss(predict(m, Xv), yv)
            msg += f"  quiz loss {vl:.4f}"
            if vl < best_loss:
                best_loss, best = vl, {k: v.copy() for k, v in m.items()}
                msg += "  <- best so far"
        log(msg + f"  ({time.time() - t0:.0f}s)")
    if best is not None:
        m.update(best)
    return m


# ---------- the exam ----------

def trading_exam(p, fw, dates, syms, spy_close):
    """Every 5 trading days: buy its top PICKS, sell 5 days later, pay slippage both ways."""
    import settings
    cost = 2 * settings.STOCK_SLIPPAGE_PCT / 100
    days = np.unique(dates)[::HORIZON]
    robot, everyone = [1.0], [1.0]
    wins = 0
    for d in days:
        on = dates == d
        if on.sum() < PICKS * 3:
            continue
        top = np.argsort(p[on])[-PICKS:]
        mine, all_ = fw[on][top].mean() - cost, fw[on].mean()
        robot.append(robot[-1] * (1 + mine))
        everyone.append(everyone[-1] * (1 + all_))
        wins += mine > all_
    spy = spy_close.loc[days[0]:days[-1]]
    rounds = len(robot) - 1
    return {"rounds": rounds, "robot": robot[-1] - 1, "everyone": everyone[-1] - 1,
            "spy": spy.iloc[-1] / spy.iloc[0] - 1, "beat_rate": wins / max(rounds, 1),
            "max_dd": float(np.min(np.array(robot) / np.maximum.accumulate(robot)) - 1)}


def weights_path(knobs):
    return f"ml_weights_{knobs}.npz"


def run(years, knobs):
    from universe import UNIVERSE
    panels = fetch_panels(UNIVERSE, years)
    f, label, fwd = build_features(panels)
    names, X, y, fw, dates, syms = stack(f, label, fwd)
    has_answer = np.isfinite(y)

    all_days = np.unique(dates[has_answer])
    cut = int(len(all_days) * TRAIN_FRAC)
    vcut = int(cut * (1 - VAL_FRAC))
    exam_start = all_days[cut]
    # drop HORIZON days before each boundary: their answers peek into the next section
    tr = has_answer & (dates < all_days[vcut - HORIZON])
    va = has_answer & (dates >= all_days[vcut]) & (dates < all_days[cut - HORIZON])
    te = has_answer & (dates >= exam_start)

    mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-8          # scaling learned from study days only
    Xn = np.clip((X - mu) / sd, -5, 5).astype(np.float32)

    rng = np.random.default_rng(42)
    m = new_model(X.shape[1], knobs, rng)
    h1, h2 = layer_sizes(X.shape[1], knobs)
    print(f"\nClues per stock per day: {len(names)}")
    print(f"Brain: {len(names)} -> {h1:,} -> {h2:,} -> 1   =   {count_knobs(m):,} knobs")
    print(f"Study {tr.sum():,} | quiz {va.sum():,} | exam {te.sum():,} examples (exam from {exam_start})\n")
    train(m, Xn[tr], y[tr], Xn[va], y[va], rng=rng)

    acc = lambda mask: np.mean((predict(m, Xn[mask]) > 0.5) == y[mask])
    p_te = predict(m, Xn[te])
    ex = trading_exam(p_te, fw[te], dates[te], syms[te], panels["close"]["SPY"])
    print(f"\nStudy accuracy: {acc(tr):.1%}   Quiz: {acc(va):.1%}   Exam: {acc(te):.1%}   (coin flip = 50%)")
    print(f"\nPRETEND TRADING EXAM ({ex['rounds']} rounds of 5 days, top {PICKS} picks, slippage paid):")
    print(f"  Robot's picks:        {ex['robot']:+.1%}   (worst drop {ex['max_dd']:.1%})")
    print(f"  Buy every stock:      {ex['everyone']:+.1%}")
    print(f"  Just hold SPY:        {ex['spy']:+.1%}")
    print(f"  Rounds robot beat 'every stock': {ex['beat_rate']:.0%}")

    today = dates.max()
    now = dates == today
    p_now = predict(m, Xn[now])
    top = np.argsort(p_now)[::-1][:PICKS]
    print(f"\nIts top {PICKS} for the next 5 days (as of {today}), opinion only:")
    for i in top:
        print(f"  {syms[now][i]:6s} {p_now[i]:.0%} chance to beat the typical stock")

    np.savez(weights_path(knobs), mu=mu, sd=sd, names=np.array(names), **m)
    print(f"\nSaved knobs to {weights_path(knobs)} (used only by --log, which never trades).")


def log_today(knobs):
    """Write today's top picks to the diary as advisory BUYs, so compare.py /
    grader.grade_all score them against the real robot over the coming days."""
    import diary
    from universe import UNIVERSE
    w = np.load(weights_path(knobs))
    m = {k: w[k] for k in ("W1", "b1", "W2", "b2", "W3", "b3")}
    panels = fetch_panels(UNIVERSE, 1)
    f, label, fwd = build_features(panels)
    names, X, y, fw, dates, syms = stack(f, label, fwd)
    assert names == list(w["names"]), "clues changed since training - retrain first"
    if dates.max() != datetime.now().date():
        print(f"No trading bar for today (latest {dates.max()}) - market closed, nothing logged.")
        return
    now = dates == dates.max()
    p = predict(m, np.clip((X[now] - w["mu"]) / w["sd"], -5, 5).astype(np.float32))
    top = np.argsort(p)[::-1][:PICKS]
    close = panels["close"].loc[dates.max()]

    db = diary.get_db()
    run_id = diary.start_run(db, "ml_advisory", STRATEGY_NAME, None, None)
    for i in top:
        sym = syms[now][i]
        diary.log_decision(db, run_id, sym, "BUY",
                           f"ML brain ({knobs:,} knobs): {p[i]:.0%} chance to beat the typical stock over 5 days",
                           False, None, None, float(close[sym]),
                           {"strategy": STRATEGY_NAME, "knobs": knobs, "prob": float(p[i]), "as_of": str(dates.max())})
        print(f"  {sym:6s} {p[i]:.0%}")
    diary.finish_run(db, run_id, None, None)
    print(f"Logged top {PICKS} as run #{run_id} ({STRATEGY_NAME}, advisory only, no orders).")


def selftest():
    rng = np.random.default_rng(0)
    for k in (10_000, 100_000, 10_000_000):
        assert abs(count_knobs(new_model(67, k, rng)) - k) <= k * 0.001, k
    m = new_model(67, 10_000_000, rng)
    small = {"W1": m["W1"][:, :64], "b1": m["b1"][:64], "W2": m["W2"][:64, :64],
             "b2": m["b2"][:64], "W3": m["W3"][:64], "b3": m["b3"]}
    X = rng.normal(size=(4000, 67)).astype(np.float32)
    y = (X[:, 0] + X[:, 1] > 0).astype(float)             # a learnable fake rule
    before = logloss(predict(small, X), y)
    train(small, X, y, epochs=20, lr=3e-3, log=lambda s: None)
    after = logloss(predict(small, X), y)
    assert after < 0.5 * before, (before, after)
    # exam math: perfect predictions should beat buying everything
    fw = rng.normal(size=600); d = np.repeat(np.arange(20), 30)
    spy = pd.Series(np.linspace(100, 110, 20), index=np.arange(20))
    ex = trading_exam(fw, fw, d, d, spy)
    assert ex["robot"] > ex["everyone"] and ex["beat_rate"] == 1.0, ex
    print(f"selftest ok: 10k/100k/10M knobs within 0.1%, learning loss {before:.3f} -> {after:.3f}, exam math ok")


if __name__ == "__main__":
    arg = lambda name, default: type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default
    knobs = arg("--knobs", 10_000)
    if "--selftest" in sys.argv:
        selftest()
    elif "--log" in sys.argv:
        log_today(knobs)
    else:
        run(arg("--years", 5.0), knobs)
