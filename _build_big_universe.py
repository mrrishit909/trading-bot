"""
One-off helper: build universe_big.py = the ~2000 most-traded US stocks the
main account may choose from, each with a sector (so the sector cap still works).

  1. Nasdaq's free screener download: every NYSE/Nasdaq/AMEX stock + its sector
  2. Keep only plain common stock that's active + tradable on Alpaca
  3. Rank by median daily dollar volume (last ~60 days of Alpaca bars),
     need price >= scanner.MIN_PRICE and enough history for the scanner
  4. Always keep the hand-picked 300 in universe.py

Re-run to refresh:  ./venv/bin/python _build_big_universe.py
"""
import os
import re
import statistics
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment

from universe import UNIVERSE
from scanner import MIN_PRICE

TARGET = 2000
MIN_BARS = 140          # scanner needs ~126 days for 6-month momentum
# Nasdaq's sector names -> the GICS-ish names sectors.py already uses
SECTOR_MAP = {
    "Finance": "Financials", "Technology": "Information Technology",
    "Basic Materials": "Materials", "Telecommunications": "Communication Services",
    "Health Care": "Health Care", "Consumer Discretionary": "Consumer Discretionary",
    "Consumer Staples": "Consumer Staples", "Industrials": "Industrials",
    "Energy": "Energy", "Utilities": "Utilities", "Real Estate": "Real Estate",
    "Miscellaneous": "Miscellaneous",
}
NOT_COMMON = re.compile(r"warrant|\bunits?\b|\brights?\b|preferred|notes due|debenture|"
                        r"\bETN\b|acquisition corp", re.I)

load_dotenv()
KEY, SEC = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")

# 1. Nasdaq screener
rows = requests.get("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&download=true",
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=60).json()["data"]["rows"]
nasdaq = {}
for r in rows:
    sym = r["symbol"].strip().replace("/", ".")
    if (r["sector"] in SECTOR_MAP and re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", sym)
            and not NOT_COMMON.search(r["name"])):
        nasdaq[sym] = SECTOR_MAP[r["sector"]]
print(f"Nasdaq screener: {len(rows)} rows -> {len(nasdaq)} plain common stocks with a sector")

# 2. tradable on Alpaca
assets = TradingClient(KEY, SEC, paper=True).get_all_assets(
    GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY))
tradable = {a.symbol for a in assets if a.tradable}
cands = sorted((set(nasdaq) & tradable) | set(UNIVERSE))
print(f"Tradable on Alpaca: {len(cands)} candidates")

# 3. rank by dollar volume
data = StockHistoricalDataClient(KEY, SEC)
start = datetime.now(timezone.utc) - timedelta(days=300)
score = {}
for i in range(0, len(cands), 200):
    chunk = cands[i:i + 200]
    bars = data.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=chunk, timeframe=TimeFrame.Day, start=start,
        adjustment=Adjustment.ALL)).data
    for s in chunk:
        b = bars.get(s, [])
        if len(b) >= MIN_BARS and b[-1].close >= MIN_PRICE:
            score[s] = statistics.median(x.close * x.volume for x in b[-60:])
    print(f"  checked {min(i + 200, len(cands))}/{len(cands)}")

keep = [s for s in UNIVERSE if s in score or s in ("SPY", "QQQ", "DIA", "IWM")]
missing = sorted(set(UNIVERSE) - set(keep))
if missing:
    print(f"  note: hand-picked names failing the data check, kept anyway: {missing}")
    keep = list(UNIVERSE)
for s in sorted(score, key=score.get, reverse=True):
    if len(keep) >= TARGET:
        break
    if s not in keep:
        keep.append(s)
keep.sort()
new_sectors = {s: nasdaq[s] for s in keep if s not in set(UNIVERSE)}
floor = min(score[s] for s in new_sectors) if new_sectors else 0

with open("universe_big.py", "w") as f:
    f.write('"""\nBIG_UNIVERSE: ~2000 most-traded US stocks for the main account.\n'
            "Built by _build_big_universe.py on " + datetime.now().strftime("%Y-%m-%d") +
            f" (hand-picked 300 from universe.py + the most-traded others,\n"
            f"smallest added name trades ~${floor / 1e6:,.0f}M/day). Re-run that script to refresh.\n\n"
            "BIG_SECTOR: sector for each name NOT already in sectors.SECTOR (from Nasdaq's screener).\n"
            '"""\n\n')
    f.write("BIG_UNIVERSE = [\n")
    for i in range(0, len(keep), 12):
        f.write("    " + ", ".join(f'"{s}"' for s in keep[i:i + 12]) + ",\n")
    f.write("]\n\nBIG_SECTOR = {\n")
    for s, sec in sorted(new_sectors.items()):
        f.write(f'    "{s}": "{sec}",\n')
    f.write("}\n")
print(f"\nwrote universe_big.py: {len(keep)} stocks ({len(new_sectors)} new), "
      f"smallest new one trades ~${floor / 1e6:,.1f}M/day")
