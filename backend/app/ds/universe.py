"""Dynamic investable universe (liquid large/mid-cap US equities + benchmarks)."""

from __future__ import annotations

# Curated liquid universe (~100 names). Expandable via API without code change.
UNIVERSE_META: dict[str, dict[str, str]] = {
    # Technology
    "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
    "MSFT": {"name": "Microsoft Corp.", "sector": "Technology"},
    "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology"},
    "AMZN": {"name": "Amazon.com Inc.", "sector": "Consumer"},
    "NVDA": {"name": "NVIDIA Corp.", "sector": "Technology"},
    "META": {"name": "Meta Platforms", "sector": "Technology"},
    "AVGO": {"name": "Broadcom Inc.", "sector": "Technology"},
    "ORCL": {"name": "Oracle Corp.", "sector": "Technology"},
    "CRM": {"name": "Salesforce Inc.", "sector": "Technology"},
    "ADBE": {"name": "Adobe Inc.", "sector": "Technology"},
    "CSCO": {"name": "Cisco Systems", "sector": "Technology"},
    "AMD": {"name": "Advanced Micro Devices", "sector": "Technology"},
    "INTC": {"name": "Intel Corp.", "sector": "Technology"},
    "QCOM": {"name": "Qualcomm Inc.", "sector": "Technology"},
    "TXN": {"name": "Texas Instruments", "sector": "Technology"},
    "IBM": {"name": "IBM Corp.", "sector": "Technology"},
    "NOW": {"name": "ServiceNow Inc.", "sector": "Technology"},
    "INTU": {"name": "Intuit Inc.", "sector": "Technology"},
    "AMAT": {"name": "Applied Materials", "sector": "Technology"},
    "MU": {"name": "Micron Technology", "sector": "Technology"},
    # Consumer
    "TSLA": {"name": "Tesla Inc.", "sector": "Consumer"},
    "HD": {"name": "Home Depot", "sector": "Consumer"},
    "MCD": {"name": "McDonald's Corp.", "sector": "Consumer"},
    "NKE": {"name": "Nike Inc.", "sector": "Consumer"},
    "SBUX": {"name": "Starbucks Corp.", "sector": "Consumer"},
    "LOW": {"name": "Lowe's Companies", "sector": "Consumer"},
    "TGT": {"name": "Target Corp.", "sector": "Consumer"},
    "BKNG": {"name": "Booking Holdings", "sector": "Consumer"},
    "CMG": {"name": "Chipotle Mexican Grill", "sector": "Consumer"},
    "TJX": {"name": "TJX Companies", "sector": "Consumer"},
    # Financials
    "JPM": {"name": "JPMorgan Chase", "sector": "Financials"},
    "V": {"name": "Visa Inc.", "sector": "Financials"},
    "MA": {"name": "Mastercard Inc.", "sector": "Financials"},
    "BAC": {"name": "Bank of America", "sector": "Financials"},
    "WFC": {"name": "Wells Fargo", "sector": "Financials"},
    "GS": {"name": "Goldman Sachs", "sector": "Financials"},
    "MS": {"name": "Morgan Stanley", "sector": "Financials"},
    "BLK": {"name": "BlackRock Inc.", "sector": "Financials"},
    "AXP": {"name": "American Express", "sector": "Financials"},
    "SCHW": {"name": "Charles Schwab", "sector": "Financials"},
    "C": {"name": "Citigroup Inc.", "sector": "Financials"},
    "SPGI": {"name": "S&P Global", "sector": "Financials"},
    # Healthcare
    "UNH": {"name": "UnitedHealth", "sector": "Healthcare"},
    "JNJ": {"name": "Johnson & Johnson", "sector": "Healthcare"},
    "LLY": {"name": "Eli Lilly", "sector": "Healthcare"},
    "ABBV": {"name": "AbbVie Inc.", "sector": "Healthcare"},
    "MRK": {"name": "Merck & Co.", "sector": "Healthcare"},
    "PFE": {"name": "Pfizer Inc.", "sector": "Healthcare"},
    "TMO": {"name": "Thermo Fisher", "sector": "Healthcare"},
    "ABT": {"name": "Abbott Laboratories", "sector": "Healthcare"},
    "DHR": {"name": "Danaher Corp.", "sector": "Healthcare"},
    "ISRG": {"name": "Intuitive Surgical", "sector": "Healthcare"},
    "AMGN": {"name": "Amgen Inc.", "sector": "Healthcare"},
    "GILD": {"name": "Gilead Sciences", "sector": "Healthcare"},
    # Energy / Industrials / Materials
    "XOM": {"name": "Exxon Mobil", "sector": "Energy"},
    "CVX": {"name": "Chevron Corp.", "sector": "Energy"},
    "COP": {"name": "ConocoPhillips", "sector": "Energy"},
    "SLB": {"name": "Schlumberger", "sector": "Energy"},
    "CAT": {"name": "Caterpillar Inc.", "sector": "Industrials"},
    "GE": {"name": "GE Aerospace", "sector": "Industrials"},
    "HON": {"name": "Honeywell", "sector": "Industrials"},
    "UPS": {"name": "United Parcel Service", "sector": "Industrials"},
    "RTX": {"name": "RTX Corp.", "sector": "Industrials"},
    "BA": {"name": "Boeing Co.", "sector": "Industrials"},
    "DE": {"name": "Deere & Co.", "sector": "Industrials"},
    "LMT": {"name": "Lockheed Martin", "sector": "Industrials"},
    "LIN": {"name": "Linde plc", "sector": "Materials"},
    "APD": {"name": "Air Products", "sector": "Materials"},
    "SHW": {"name": "Sherwin-Williams", "sector": "Materials"},
    # Communication / Staples / Utilities / REITs
    "NFLX": {"name": "Netflix Inc.", "sector": "Communication"},
    "DIS": {"name": "Walt Disney", "sector": "Communication"},
    "CMCSA": {"name": "Comcast Corp.", "sector": "Communication"},
    "T": {"name": "AT&T Inc.", "sector": "Communication"},
    "VZ": {"name": "Verizon Communications", "sector": "Communication"},
    "PG": {"name": "Procter & Gamble", "sector": "Staples"},
    "KO": {"name": "Coca-Cola Co.", "sector": "Staples"},
    "PEP": {"name": "PepsiCo Inc.", "sector": "Staples"},
    "COST": {"name": "Costco Wholesale", "sector": "Staples"},
    "WMT": {"name": "Walmart Inc.", "sector": "Staples"},
    "PM": {"name": "Philip Morris", "sector": "Staples"},
    "NEE": {"name": "NextEra Energy", "sector": "Utilities"},
    "DUK": {"name": "Duke Energy", "sector": "Utilities"},
    "SO": {"name": "Southern Company", "sector": "Utilities"},
    "AMT": {"name": "American Tower", "sector": "Real Estate"},
    "PLD": {"name": "Prologis Inc.", "sector": "Real Estate"},
    "EQIX": {"name": "Equinix Inc.", "sector": "Real Estate"},
    # Benchmarks
    "SPY": {"name": "S&P 500 ETF", "sector": "Index"},
    "QQQ": {"name": "Nasdaq-100 ETF", "sector": "Index"},
    "IWM": {"name": "Russell 2000 ETF", "sector": "Index"},
    "DIA": {"name": "Dow Jones ETF", "sector": "Index"},
    "TLT": {"name": "20+ Year Treasury ETF", "sector": "Index"},
    "GLD": {"name": "Gold ETF", "sector": "Index"},
    "HYG": {"name": "High Yield Bond ETF", "sector": "Index"},
}


def list_universe(include_index: bool = True, limit: int | None = None) -> list[dict]:
    rows = [
        {"symbol": s, "name": m["name"], "sector": m["sector"]}
        for s, m in UNIVERSE_META.items()
        if include_index or m["sector"] != "Index"
    ]
    if limit:
        rows = rows[:limit]
    return rows


def equity_symbols(limit: int | None = None) -> list[str]:
    syms = [s for s, m in UNIVERSE_META.items() if m["sector"] != "Index"]
    return syms[:limit] if limit else syms


def index_symbols() -> list[str]:
    return [s for s, m in UNIVERSE_META.items() if m["sector"] == "Index"]


def meta_for(symbol: str) -> dict[str, str]:
    return UNIVERSE_META.get(symbol.upper(), {"name": symbol.upper(), "sector": "Unknown"})
