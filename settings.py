"""
The robot's rules, all in one place. Change these numbers to make the
robot braver or more careful. Start SMALL and CAREFUL.
"""

from universe_big import BIG_UNIVERSE
from crypto_universe import CRYPTO_UNIVERSE   # noqa: F401  (used by the crypto robot)

# The robot may ONLY trade stocks on this list: the ~2000 most-traded US stocks
# (universe_big.py, built by _build_big_universe.py; includes the hand-picked 300
# in universe.py, which the $500 sprint account still uses — see profiles.py).
ALLOWED_STOCKS = BIG_UNIVERSE

# Never put more than this many dollars into one stock.
# (vol-sizing can push a calm-stock buy up to 1.4 x DOLLARS_PER_BUY = $5,600.)
MAX_DOLLARS_PER_STOCK = 6000

# How many dollars to spend each time the robot buys a stock.
DOLLARS_PER_BUY = 4000

# Never own more than this many different stocks at once.
# 15 x $4,000 = ~$60,000 in stocks when fully invested (~60% of the $100k account;
# raised from 10 x $2,500 = $25k on 2026-09-28 at the user's request).
# The old 8 x $1,500 = ~$12k left the account ~88% in cash through an up market
# (backtest + daily reviews, Sept 2026): the underperformance was almost entirely
# "not participating", not bad stock-picking.
MAX_STOCKS_HELD = 15

# Emergency exit: if a stock we hold falls more than this % below what we PAID,
# sell it right now, no matter what the averages say. Catches overnight crashes
# and bad-news gaps that the slow 20-day average would take days to react to.
STOCK_STOP_LOSS_PCT = 10

# Trailing stop: ONLY when a position is profitable — if it falls this % below
# its own recent high, lock in the gain instead of waiting for the slow SMA to
# catch up and give it all back. (Losing positions are handled by the stop-loss
# above and the SMA-reversal exit, not this.)
TRAILING_STOP_PCT = 10

# Never make more than this many trades in one day (stocks AND options together).
# Up to 15 stock buys + 15 stock sells + a few option closes = ~36 worst case.
MAX_TRADES_PER_DAY = 45

# If we lose more than this much pretend money in one day, STOP everything.
# With the SPY cash sleeve on, ~$88k is working (stocks + SPY sleeve + crypto),
# so a 2.5% down day = ~$2,200; 3000 keeps a normal red day from freezing the bot
# while still halting a genuine ~3.5%+ rout. (Only blocks BUYS; sells always allowed.)
DAILY_LOSS_LIMIT = 3000

# When scanning the big list, how many top candidates to look at closely.
# Kept well above MAX_STOCKS_HELD: cooldown/news/sector filters knock some out.
SHORTLIST_SIZE = 25

# ---- signals & filters (see scanner.py) ----
# Rank buys by longer-horizon momentum (3- and 6-month total return), not just
# the last week's move. Multi-month momentum is one of the most reliable edges
# in markets; a 1-week pop mostly mean-reverts.
USE_MOMENTUM_RANK = True

# Only buy something that is also UP over the past quarter (positive 63-day
# return). Don't catch a falling knife just because it bounced this week.
REQUIRE_POSITIVE_QUARTER = True

# Skip a buy if the 14-day RSI is above this — the move is already stretched
# and a pullback is likely. (Applies to stocks and crypto.)
RSI_OVERBOUGHT = 78

# Skip a buy if its ATR%(14) is above this (too jumpy). None = no filter.
# The daily reviews flagged high-ATR names as disproportionately the losers
# (e.g. HOOD, 2026-09-16) more than once. Backtested 2026-09-17 over grid
# {3,4,5,6,7,10} vs the no-filter baseline (+10.4% total, -6.0% dd, 44% win,
# +1.58% avg trade, 2.1yr to 2026-09-17): 5 was the clear best — +14.0% total,
# -5.8% dd, 47% win, +2.41% avg trade — and not monotonic with the cap (3 and
# 4 were worse), which argues it's a real pattern near this ATR range, not
# just "fewer trades." Still loses to SPY by ~32pts either way — this is a
# same-strategy improvement, not a fix for the momentum sleeve's core
# underperformance. One historical path; revisit if live results diverge.
MAX_BUY_ATR_PCT = 5

# Exit side of REQUIRE_POSITIVE_QUARTER: sell a HELD stock if its 3-month
# momentum has broken down this hard, even if the short 5/20-day average still
# says "trending up" — a short-term bounce inside a real quarter-long downtrend
# (found by the 2026-09-03 daily review: ORCL held "trending up" at -36% 3mo).
MOMENTUM_BREAKDOWN_PCT = 20
CRYPTO_MOMENTUM_BREAKDOWN_PCT = 25   # crypto's own 30-day momentum, wider band

# Volatility-adaptive stop-loss: the stop sits this many ATRs below entry, but
# never looser than STOCK_STOP_LOSS_PCT and never tighter than 4%. Calm stocks
# get a tight stop, jumpy ones get room to breathe.
USE_ATR_STOP = True
STOCK_STOP_ATR_MULT = 2.5

# Scale out of winners: the FIRST time a held position is up at least
# SCALE_OUT_GAIN_PCT, sell SCALE_OUT_FRACTION of it and let the rest ride (the
# trailing stop then protects a locked-in gain). Happens at most once per
# holding period.
#
# OFF by default: the backtest (2.1yr, to 2026-09-09) said this COSTS return in
# a trending market — clipping winners at +20% gave +9.5% total / -5.9% max
# drawdown vs +10.4% / -6.3% with it off. It trades ~1 point of return for ~0.4
# points less drawdown. The machinery is here and tested; flip it on if a
# smoother equity curve is worth more to you than the backtest's edge.
SCALE_OUT_ENABLED = False
SCALE_OUT_GAIN_PCT = 20
SCALE_OUT_FRACTION = 0.4

# Size each stock buy by its volatility so every position carries similar risk:
# spend  DOLLARS_PER_BUY x (TARGET_VOL_PCT / the stock's own ATR%), clamped to
# [VOL_SIZING_MIN, VOL_SIZING_MAX]. The floor is 0.6 (not 0.5) so a strong,
# jumpy momentum name — exactly the kind this strategy wants — doesn't get
# shrunk to a token position (UNI was +48% and the smallest holding in the book).
USE_VOL_SIZING = True
TARGET_VOL_PCT = 2.5
VOL_SIZING_MIN = 0.6
VOL_SIZING_MAX = 1.4

# ---- refinements (both accounts) ----
# Market-regime filter: only BUY stocks when the S&P 500 itself is in an uptrend.
# Trend-following gets chopped to pieces in a falling market — in that regime we
# only manage and exit what we already hold, and buy nothing.
#
# The gate is SPY's own 63-day (one-quarter) total return. The old gate was
# SPY's 5-day average vs its 20-day — a hair-trigger that flipped false on every
# shallow pullback and kept the bot 100% in cash for the 11 trading days after
# 2026-08-28 while SPY was +4.7% over 3 months (flagged in four daily reviews).
# A quarter-return gate answers the actual question ("is the market broadly
# rising?") and rides through normal dips. -3% (not 0) leaves a small buffer so
# one bad week doesn't slam the gate shut.
USE_MARKET_FILTER = True
MARKET_TREND_MIN_MOM63 = -3.0

# Volatility "risk-off" filter — a free stand-in for watching the VIX: SPY's
# own ATR% (its daily trading range as a % of price) is a real, no-account-
# needed measure of how turbulent the market is right now. Calibrated against
# 3 years of SPY history (2026-09-04): median 1.07%, p90 1.82%, p95 2.74%,
# crisis spikes 4-7%+. 2.5% (~p95) catches only genuine turbulence. The old 1.8%
# (p90) also blocked buying on any slightly-jumpy-but-fine week, compounding the
# too-tight trend gate above and keeping the bot parked in cash.
USE_VOLATILITY_FILTER = True
MAX_MARKET_ATR_PCT = 2.5

# Re-buy cooldown: after SELLING a name, don't buy it again for this many days.
# Stops the sell-it-then-rebuy-a-bit-higher whipsaw.
REBUY_COOLDOWN_DAYS = 4

# Rank-based rotation: when all MAX_STOCKS_HELD slots are full, a much
# stronger new candidate can otherwise sit outside the book indefinitely just
# because weaker names got there first — the daily reviews caught this in
# practice: MRNA sat at #1 momentum (+190%+) for 3+ straight days, cooldown
# long lapsed, permanently blocked because the book was full of weaker names
# that hadn't (yet) triggered a real exit. If the best waiting candidate beats
# the weakest HELD name's own momentum score by ROTATION_MARGIN_PTS, sell the
# weakest and buy the best candidate instead of just waiting. Deliberately NOT
# sector-matched: the freed slot goes through the normal BUY loop, which
# already enforces MAX_STOCKS_PER_SECTOR — so if the weakest held name's own
# sector is already at/over cap, freeing it also nudges that sector back
# toward the limit over time (self-heals a sector that crept over cap from
# trades made before the cap existed) instead of perpetuating the overweight
# by swapping in another name from that same already-full sector. One
# consequence: if every top candidate's sector is already at cap, the freed
# slot may sit in cash for a run or two rather than force-feed one sector —
# that's the sector cap doing its job, not a bug. Guarded by a minimum hold
# time so it can't be used to churn a name bought yesterday.
#
# Turned OFF 2026-09-22. It shipped ON in good faith (see git-free history in
# this comment) but four straight live daily reviews caught it doing the
# opposite of its intent: BBY, HOOD, NOW, MSFT, AAPL and ILMN were all rotated
# out at flat-or-negative returns and, in three cases (AAPL, ILMN twice), the
# very name it sold immediately re-ranked #1 momentum days later — a sold-low,
# rebought-high round trip on ILMN (200.90 -> 242.25, +20.6%) being the
# clearest case. A same-window backtest (2024-08-15 to 2026-09-22, 527 sim
# days) confirms it isn't a fluke: rotation ON = +12.6% total / -5.9% dd / 45%
# win / +2.13% avg trade / 283 trades; rotation OFF = +13.2% total / -5.6% dd
# / 46% win / +2.62% avg trade / 237 trades. Off wins on every axis — better
# return, lower drawdown, higher win rate, bigger average trade, fewer round
# trips. Raising ROTATION_MIN_HOLD_DAYS (7 or 10) or ROTATION_MARGIN_PTS (75)
# were also tried and only partially recovered the gap; neither beat OFF
# outright. The original motivating case (MRNA locked out for days) is real
# but rarer than the churn it causes — the mechanism as built can't tell
# "genuine high-conviction override" apart from "routine reshuffling" cheaply
# enough, so it went net negative. Note this does NOT fix the strategy's core
# problem: even with rotation off, the backtest still loses to SPY buy-and-hold
# by ~30 points over the same window — this removes a real leak, it doesn't
# close the gap to the benchmark.
USE_RANK_ROTATION = False
ROTATION_MARGIN_PTS = 50
ROTATION_MIN_HOLD_DAYS = 3

# Sector cap: never hold more than this many stocks from the same sector at
# once (see sectors.py) — so "8 positions" can't quietly mean "8 tech stocks".
# ETFs (SPY/QQQ/DIA/IWM) don't count against this.
MAX_STOCKS_PER_SECTOR = 3

# SPY cash sleeve: park idle cash in SPY instead of letting it sit (the backtest
# and daily reviews showed the bot mostly lost to SPY by "not participating").
# Keeps SPY_SLEEVE_BUFFER in real cash for crypto buys; sells SPY to fund stock
# buys; only trades the sleeve when it's SPY_SLEEVE_MIN_TRADE off target so the
# 30-min schedule doesn't churn. SPY in the sleeve is NOT a "holding": it's
# ignored by the sell rules, MAX_STOCKS_HELD, and the per-stock cap.
# Turned on 2026-09-29 as variant "C" after a same-window backtest on the 2000
# list (2024-08 -> 2026-09): no sleeve +24.2% / -9.7% dd; always-in sleeve
# +51.3% / -19.7% dd; sleeve w/ risk-off exit +41.1% / -13.2% dd (SPY +41.2%).
# Both sleeves beat no-sleeve in each half of the window. C picked for the
# smaller drawdown; set RISK_OFF_EXIT False for the higher-return/bigger-dd B.
USE_SPY_CASH_SLEEVE = True
SPY_SLEEVE_BUFFER = 12000          # real cash kept for crypto (4 x $1,500) + a couple of stock buys
SPY_SLEEVE_MIN_TRADE = 2000
SPY_SLEEVE_RISK_OFF_EXIT = True    # move the sleeve to cash when the market-trend/volatility gate fails

# Pre-market news filter (see news_scan.py — runs ~8:45am ET, writes news/DATE.json):
#   - pause ALL new stock buys when the market read is "risk_off"
#   - don't buy a candidate whose overnight news is "avoid" or "negative"
#   - SELL a held stock whose news is "avoid" (clear disaster) even if the chart holds
# Degrades safely: if today's news file is missing/stale, the bot just trades on
# the momentum signals alone. Live-only — the backtest can't replay news sentiment.
USE_NEWS_FILTER = True

# Don't chase a blow-off top: skip a crypto buy if the coin is already up more
# than this in a single day (it's likely to snap back).
CRYPTO_CHASE_LIMIT_PCT = 25

# ---- realism haircut for grading (see grader.py) ----
# Paper fills are optimistic — no bid/ask spread, no slippage, no commission.
# The Scoreboard and backtest apply this % against you on BOTH the buy and the
# sell of every round trip, so "beat SPY" reflects something closer to real
# trading, not a best-case fill. Does not affect what the bot actually trades.
STOCK_SLIPPAGE_PCT = 0.05
CRYPTO_SLIPPAGE_PCT = 0.15
OPTION_SLIPPAGE_PCT = 1.0   # options spreads are much wider


# ============ AI ADVISOR — PAUSED ============
# step9 asks Claude for a BUY/SELL/WAIT opinion on every held stock + the
# scanner's shortlist, twice a weekday. It NEVER trades — the calls just go in
# the diary so grade_all can score them against the mechanical scanner
# (sma_scan_v1). Cost was never the issue (~$0.80/month) — this was always
# "pause it if the grading says it's not adding anything" (see daily_review.py
# _notes). It matured on 2026-09-14: 270 judged decisions vs the scanner's own
# 84, and the advisor's hit rate is 31.0% against the scanner's 56.3% — a 25-
# point gap that WIDENED as the sample grew (was already 12 points behind at
# 30/21 judged on 09-11). That's a real, growing sample, not noise. Paused.
# Flip back to True to resume (no schedule change needed either way).
AI_ADVISOR_ENABLED = False

# ============ OPTIONS — TURNED OFF ============
# Options trading is disabled. The options robot (step11) now only runs to
# CLOSE any bets still open, then does nothing. Flip this back to True to
# re-enable the "stock replacement" strategy (deep ITM, long-dated calls/puts).

TRADE_OPTIONS = False

# ITM long-dated contracts cost more, so: fewer bets, a bit more each.
# One contract on a stock priced over ~$220 will usually blow this budget and
# get skipped — that's fine, the bot just bets on cheaper names instead.
MAX_DOLLARS_PER_OPTION = 2000     # most we'll pay for one contract
MAX_OPTION_POSITIONS = 2          # ~$4k of options exposure at most

# Which expirations to consider (days from today). Far out = gentle time-decay.
OPTION_MIN_DAYS = 60
OPTION_MAX_DAYS = 120

# How far IN the money to buy (percent). Call strike this far BELOW the stock
# price; put strike this far ABOVE. ITM = high delta, much less time-value to
# bleed away. 5% keeps delta ~0.65 while staying affordable on most stocks.
OPTION_ITM_PCT = 5.0

# Skip contracts fewer people are trading than this (hard to get out of).
OPTION_MIN_OPEN_INTEREST = 100

# Only OPEN a bet if the fresh crossover has real momentum behind it
# (the stock's 5-day move must be at least this big, in the bet's direction).
OPTION_MIN_MOMENTUM_PCT = 3.0

# Only buy calls when SPY is also trending up; only buy puts when SPY is not.
OPTION_USE_MARKET_FILTER = True

# Exits (the MAIN exit is "the trend that justified the bet has reversed",
# checked with the same 5/20 SMA signal the stock robot uses):
OPTION_DISASTER_STOP_PCT = 65         # sell to close if down this much (floor)
OPTION_CLOSE_BEFORE_EXPIRY_DAYS = 10  # always close if expiry is this close


# ============ CRYPTO (paper only, trades 24/7) ============
# Crypto never closes, so this part of the robot never has to stop.
# Crypto is jumpier than stocks, so the money limits are smaller.

TRADE_CRYPTO = True

# How many dollars to spend each time it buys a coin.
# 4 x $1,250 = ~$5,000 in crypto when fully invested.
CRYPTO_DOLLARS_PER_BUY = 1250

# Never own more than this many different coins at once.
MAX_CRYPTO_HELD = 4

# Never put more than this many dollars into one coin.
MAX_DOLLARS_PER_CRYPTO = 1500

# Emergency exit for crypto (wider than stocks — coins swing 10-15% in a normal
# day, so a tight stop would just sell everything constantly).
CRYPTO_STOP_LOSS_PCT = 20

# Trailing stop for crypto (wider than stocks, same idea: only when profitable).
CRYPTO_TRAILING_STOP_PCT = 15

# Never make more than this many crypto trades in one day.
MAX_CRYPTO_TRADES_PER_DAY = 8


# ============ ACCOUNT PROFILE OVERRIDES ============
# If we're running a non-"main" account (see profiles.py), replace the values
# above with that profile's overrides. The main $100k account is untouched.
import os as _os  # noqa: E402
_PROFILE = _os.environ.get("ROBOT_PROFILE", "main")
if _PROFILE != "main":
    from profiles import PROFILES as _PROFILES  # noqa: E402
    for _k, _v in _PROFILES.get(_PROFILE, {}).get("overrides", {}).items():
        globals()[_k] = _v
