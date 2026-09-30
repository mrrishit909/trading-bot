"""
One-off helper: take a big candidate list of well-known US large-caps,
check each one is real + tradable on Alpaca AND has enough daily-bar
history for the scanner, then print a clean Python list we can paste
into universe.py. Safe to delete after.
"""
import os
from dotenv import load_dotenv
load_dotenv()

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta

KEY = os.getenv("ALPACA_API_KEY")
SEC = os.getenv("ALPACA_SECRET_KEY")
trading = TradingClient(KEY, SEC, paper=True)
data = StockHistoricalDataClient(KEY, SEC)

CANDIDATES = [
 # tech / hardware / semis
 "AAPL","MSFT","NVDA","AVGO","ORCL","CRM","ADBE","AMD","CSCO","ACN","INTC","QCOM",
 "TXN","IBM","NOW","INTU","MU","AMAT","LRCX","KLAC","ADI","MRVL","NXPI","MCHP","ON",
 "MPWR","SWKS","QRVO","TER","ENPH","FSLR","SNPS","CDNS","ANSS","ROP","APH","TEL",
 "GLW","HPQ","HPE","DELL","WDC","STX","SMCI","ARM","PANW","CRWD","FTNT","ZS","NET",
 "DDOG","SNOW","MDB","TEAM","WDAY","HUBS","ADSK","PTC","TYL","CDW","IT","GRMN",
 "KEYS","TDY","ZBRA","TRMB","GEN","CTSH","EPAM","AKAM","VRSN","FFIV","GDDY","MSI",
 "JBL","FLEX","SANM","PLTR",
 # fintech / payments / financial data
 "V","MA","PYPL","FIS","FI","GPN","JKHY","BR","CPAY","ADP","PAYX","PAYC","MSCI",
 "SPGI","MCO","FDS","VRSK","EFX","NDAQ","ICE","CME","CBOE","TW","MKTX","COIN","HOOD",
 # communication / media
 "GOOGL","GOOG","META","NFLX","DIS","CMCSA","T","VZ","TMUS","CHTR","WBD","PARA",
 "FOXA","FOX","OMC","IPG","EA","TTWO","LYV","NWSA","MTCH","PINS","SNAP","RBLX",
 "SPOT","TTD","Z",
 # consumer discretionary
 "AMZN","TSLA","HD","LOW","MCD","NKE","SBUX","TJX","BKNG","MAR","HLT","CMG","LULU",
 "ORLY","AZO","ROST","DG","DLTR","YUM","DPZ","DRI","F","GM","RIVN","LCID","EBAY",
 "ETSY","W","RL","TPR","LEN","DHI","PHM","NVR","WHR","LKQ","GPC","APTV","BWA","HAS",
 "MAT","POOL","EXPE","ABNB","UBER","DASH","RCL","CCL","NCLH","WYNN","LVS","MGM",
 "CZR","DKNG","KMX","ULTA","BBY","TSCO","GNRC",
 # consumer staples
 "WMT","COST","PG","KO","PEP","PM","MO","CL","MDLZ","KDP","KMB","GIS","K","HSY",
 "STZ","KHC","SYY","KR","ADM","MKC","CLX","CHD","CAG","CPB","HRL","TSN","TAP",
 "KVUE","EL","TGT","MNST","BG","WBA",
 # health care
 "LLY","UNH","JNJ","ABBV","MRK","TMO","ABT","DHR","PFE","AMGN","GILD","BMY","ISRG",
 "VRTX","MDT","CVS","CI","HUM","CNC","ELV","MCK","COR","CAH","HCA","UHS","DVA","BDX",
 "BAX","EW","SYK","ZBH","BSX","RMD","ALGN","DXCM","IDXX","IQV","A","WAT","MTD","RVTY",
 "BIO","TECH","CRL","ILMN","BIIB","MRNA","REGN","ZTS","PODD","HOLX","STE","COO",
 "XRAY","INCY","TFX","GEHC","SOLV","VTRS",
 # financials
 "BRK.B","JPM","BAC","WFC","GS","MS","C","AXP","BLK","SCHW","USB","PNC","TFC","COF",
 "BK","STT","NTRS","RF","CFG","KEY","FITB","HBAN","MTB","ALLY","SYF","DFS","TROW",
 "BEN","IVZ","AMP","RJF","PFG","MET","PRU","AFL","ALL","TRV","CB","PGR","HIG","CINF",
 "WRB","L","AIG","ACGL","MMC","AON","AJG","BRO","GL","EG","KKR","BX","APO","ARES","OWL",
 # industrials
 "CAT","GE","HON","UNP","RTX","DE","LMT","BA","UPS","GD","NOC","LHX","TDG","HWM",
 "TXT","EMR","ETN","PH","ROK","DOV","IEX","XYL","AME","FTV","ITW","PCAR","CMI","PNR",
 "NDSN","IR","GGG","CSX","NSC","FDX","CHRW","EXPD","JBHT","ODFL","URI","WM","RSG",
 "LDOS","BAH","JCI","CARR","OTIS","TT","DAL","UAL","LUV","AAL","HII","AXON","BLDR",
 "PWR","MAS","ALLE","SNA","SWK","FAST","GWW","CTAS","VLTO","WAB","J","ACM","EME","RRX","DAY",
 # energy
 "XOM","CVX","COP","EOG","SLB","MPC","PSX","VLO","OXY","WMB","KMI","OKE","HES","HAL",
 "BKR","DVN","FANG","CTRA","APA","EQT","TRGP","LNG","EXE",
 # utilities
 "NEE","DUK","SO","D","AEP","EXC","XEL","SRE","PEG","ED","WEC","ES","EIX","DTE","PPL",
 "AEE","CMS","CNP","ATO","LNT","NI","EVRG","PNW","AES","FE","VST","CEG","NRG",
 # materials
 "LIN","APD","SHW","ECL","FCX","NEM","NUE","STLD","DOW","DD","PPG","IFF","ALB","CE",
 "CF","MOS","FMC","VMC","MLM","PKG","IP","AVY","BALL","AMCR","CTVA","EMN","LYB","SW",
 # real estate
 "PLD","AMT","EQIX","CCI","PSA","O","WELL","DLR","SPG","VICI","SBAC","EXR","AVB",
 "EQR","INVH","MAA","ESS","UDR","CPT","ARE","VTR","DOC","BXP","KIM","REG","FRT",
 "HST","CBRE","WY",
 # broad-market ETFs
 "SPY","QQQ","DIA","IWM",
]

# de-dupe, keep order
seen = set()
cands = [c for c in CANDIDATES if not (c in seen or seen.add(c))]
print(f"{len(cands)} unique candidates")

# 1) tradable check
good_asset = []
bad_asset = []
for sym in cands:
    try:
        a = trading.get_asset(sym)
        if a.tradable and str(a.status).lower().endswith("active"):
            good_asset.append(sym)
        else:
            bad_asset.append((sym, f"status={a.status} tradable={a.tradable}"))
    except Exception as e:
        bad_asset.append((sym, f"{type(e).__name__}"))

print(f"\ntradable on Alpaca: {len(good_asset)}")
if bad_asset:
    print("DROPPED (not tradable / unknown):")
    for s, why in bad_asset:
        print(f"  {s}: {why}")

# 2) enough daily-bar history + rank by average daily dollar volume,
#    then keep the biggest / most-liquid TARGET names.
TARGET = 300
end = datetime.now()
start = end - timedelta(days=90)
liq = {}          # sym -> avg daily $ volume
no_data = []
BATCH = 100
for i in range(0, len(good_asset), BATCH):
    chunk = good_asset[i:i+BATCH]
    req = StockBarsRequest(symbol_or_symbols=chunk, timeframe=TimeFrame.Day,
                           start=start, end=end)
    bars = data.get_stock_bars(req).data
    for sym in chunk:
        b = bars.get(sym, [])
        if len(b) >= 25:
            recent = b[-20:]
            liq[sym] = sum(x.close * x.volume for x in recent) / len(recent)
        else:
            no_data.append((sym, len(b)))

print(f"\nenough history: {len(liq)}")
if no_data:
    print("DROPPED (thin/no bars):")
    for s, n in no_data:
        print(f"  {s}: {n} bars")

ranked = sorted(liq, key=liq.get, reverse=True)
final = sorted(ranked[:TARGET])          # alpha order for the file
cut = ranked[TARGET:]

print(f"\nCUT for being least liquid ({len(cut)}): {', '.join(cut)}")
print(f"\n==== FINAL {len(final)} (top {TARGET} by $ volume) ====")
for i in range(0, len(final), 12):
    print("    " + ", ".join(f'"{s}"' for s in final[i:i+12]) + ",")
