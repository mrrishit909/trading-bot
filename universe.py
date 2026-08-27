"""
The "big list" — the stocks the robot is allowed to consider.

These are all large, well-known, easy-to-trade US companies (plus a few
index funds). No penny stocks, no weird stuff. The robot can ONLY ever
touch something on this list.

Add or remove tickers freely. Keep them big and liquid.
"""

UNIVERSE = [
    # --- Tech ---
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "ORCL", "CRM",
    "ADBE", "AMD", "CSCO", "ACN", "INTC", "QCOM", "TXN", "IBM", "NOW", "INTU",
    # --- Communication / media ---
    "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS",
    # --- Consumer ---
    "WMT", "COST", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW",
    # --- Staples ---
    "PG", "KO", "PEP", "PM", "MO", "CL",
    # --- Health care ---
    "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "AMGN",
    # --- Financials ---
    "BRK.B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "BLK", "SPGI",
    # --- Industrials ---
    "CAT", "GE", "HON", "UNP", "RTX", "DE", "LMT",
    # --- Energy ---
    "XOM", "CVX", "COP",
    # --- Index funds ---
    "SPY", "QQQ", "DIA",
]
