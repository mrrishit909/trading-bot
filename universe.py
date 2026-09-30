"""
The "big list" — the stocks the robot is allowed to consider.

300 large, liquid US names (the ~500 best-known large-caps, trimmed to the
top 300 by average daily dollar-volume so everything here trades easily).
Plus a few broad-market ETFs. No penny stocks, no weird stuff. The robot
can ONLY ever touch something on this list.

Built/validated 2026-08-28 with _build_universe.py — every ticker was
checked live: active + tradable on Alpaca, with enough daily-bar history
for the scanner. Re-run that script to refresh.

Add or remove tickers freely. Keep them big and liquid.
"""

UNIVERSE = [
    "A", "AAL", "AAPL", "ABBV", "ABNB", "ABT", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK",
    "AEP", "AJG", "AKAM", "ALB", "ALL", "AMAT", "AMD", "AME", "AMGN", "AMT", "AMZN", "AON",
    "APH", "APO", "ARES", "ARM", "AVGO", "AXON", "AXP", "AZO", "BA", "BAC", "BBY", "BDX",
    "BKNG", "BKR", "BLK", "BMY", "BRK.B", "BSX", "BX", "C", "CAH", "CARR", "CAT", "CB",
    "CCL", "CDNS", "CDW", "CEG", "CF", "CHTR", "CI", "CL", "CMCSA", "CME", "CMG", "CMI",
    "COF", "COIN", "COP", "COR", "COST", "CRM", "CRWD", "CSCO", "CSX", "CTAS", "CTSH", "CTVA",
    "CVS", "CVX", "DAL", "DASH", "DDOG", "DE", "DELL", "DHR", "DIA", "DIS", "DKNG", "DLR",
    "DLTR", "DUK", "DVN", "DXCM", "EBAY", "ECL", "EL", "ELV", "EME", "EMR", "EOG", "EQIX",
    "EQT", "ETN", "EXPE", "F", "FANG", "FAST", "FCX", "FDX", "FITB", "FLEX", "FOXA", "FSLR",
    "FTNT", "GD", "GE", "GILD", "GIS", "GLW", "GM", "GOOG", "GOOGL", "GPN", "GS", "GWW",
    "HAL", "HBAN", "HCA", "HD", "HLT", "HON", "HOOD", "HPE", "HPQ", "HUBS", "HUM", "HWM",
    "IBM", "ICE", "IDXX", "ILMN", "INTC", "INTU", "IQV", "IR", "ISRG", "IT", "IWM", "JBL",
    "JCI", "JNJ", "JPM", "KDP", "KEYS", "KHC", "KKR", "KLAC", "KMB", "KMI", "KO", "KR",
    "KVUE", "LHX", "LIN", "LLY", "LMT", "LNG", "LOW", "LRCX", "LULU", "LYV", "MA", "MAR",
    "MCD", "MCHP", "MCK", "MCO", "MDB", "MDLZ", "MDT", "MET", "META", "MLM", "MNST", "MO",
    "MPC", "MPWR", "MRK", "MRNA", "MRVL", "MS", "MSCI", "MSFT", "MSI", "MU", "NEE", "NEM",
    "NET", "NFLX", "NKE", "NOC", "NOW", "NRG", "NSC", "NUE", "NVDA", "NXPI", "O", "ODFL",
    "OKE", "ON", "ORCL", "ORLY", "OXY", "PANW", "PCAR", "PEP", "PFE", "PG", "PGR", "PH",
    "PLD", "PLTR", "PM", "PNC", "PPL", "PSX", "PWR", "PYPL", "QCOM", "QQQ", "RBLX", "RCL",
    "REGN", "RIVN", "RMD", "ROK", "ROP", "ROST", "RSG", "RTX", "SBUX", "SCHW", "SHW", "SLB",
    "SMCI", "SNOW", "SNPS", "SO", "SPGI", "SPOT", "SPY", "SRE", "STLD", "STX", "SWKS", "SYK",
    "T", "TDG", "TEAM", "TEL", "TER", "TFC", "TGT", "TJX", "TMO", "TMUS", "TPR", "TRGP",
    "TRV", "TSCO", "TSLA", "TT", "TTD", "TTWO", "TXN", "UAL", "UBER", "ULTA", "UNH", "UNP",
    "UPS", "URI", "USB", "V", "VLO", "VRTX", "VST", "VZ", "W", "WAT", "WBD", "WDAY",
    "WDC", "WELL", "WFC", "WM", "WMB", "WMT", "XEL", "XOM", "YUM", "ZBRA", "ZS", "ZTS",
]
