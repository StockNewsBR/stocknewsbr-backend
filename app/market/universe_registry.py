from __future__ import annotations

import copy
from typing import Any

from app.services.symbol_registry import US_EXCHANGE_BY_SYMBOL, provider_symbol


B3_PUBLIC_UNIVERSE = (
    "ITUB4", "BBDC4", "BBAS3", "SANB11", "BPAC11", "VALE3", "PETR4", "PETR3", "SUZB3", "KLBN11",
    "AXIA3", "AXIA7", "CPFE3", "EQTL3", "MGLU3", "LREN3", "AMER3", "VIIA3", "ASAI3", "WEGE3",
    "GGBR4", "CSNA3", "USIM5", "TOTS3", "POSI3", "RAIL3", "CCRO3", "NTCO3", "ABEV3", "B3SA3",
    "BBSE3", "BRAP4", "CMIG4", "COGN3", "CPLE3", "CSAN3", "CYRE3", "DXCO3",
    "EMBJ3", "ENEV3", "ENGI11", "EZTC3", "HAPV3", "HYPE3", "IRBR3", "JBSS32", "MBRF3", "MRVE3",
    "MULT3", "PCAR3", "PRIO3", "RADL3", "RAIZ4", "RDOR3", "RENT3", "BRAV3", "SBSP3", "SLCE3",
    "SMTO3", "TAEE11", "TIMS3", "UGPA3", "VBBR3", "VIVT3", "YDUQ3", "IVVB11",
)
BDR_PUBLIC_UNIVERSE = (
    "AAPL34", "MSFT34", "GOGL34", "AMZO34", "NVDC34", "TSLA34", "M1TA34", "NFLX34", "ITLC34", "A1MD34", "QCOM34",
)
CRYPTO_PUBLIC_UNIVERSE = ("BTCUSD", "ETHUSD", "BNBUSD", "SOLUSD", "XRPUSD", "ADAUSD", "DOGEUSD")
USA_PUBLIC_UNIVERSE = (
    "F", "AAL", "BA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "SPCX", "AMD", "INTC",
    "AVGO", "TSM", "JPM", "BAC", "GS", "XOM", "CVX", "COST", "WMT", "DIS", "CRM", "SNOW", "PLTR",
    "TTWO", "RACE", "LCID", "SAP", "UBER", "BYDDY", "GME", "COIN",
)

PUBLIC_UNIVERSES = {
    "B3": B3_PUBLIC_UNIVERSE,
    "BDR": BDR_PUBLIC_UNIVERSE,
    "Crypto": CRYPTO_PUBLIC_UNIVERSE,
    "USA": USA_PUBLIC_UNIVERSE,
}

# Market-context indices: display-only, never watchlist/tradable items, so they stay
# out of PUBLIC_UNIVERSES (get_all_assets feeds the user watchlist universe).
# (canonical, provider, display_name, currency)
INDEX_UNIVERSE = (
    ("IBOV", "^BVSP", "Ibovespa", "BRL"),
    ("SP500", "^GSPC", "S&P 500", "USD"),
    ("NASDAQ", "^IXIC", "Nasdaq", "USD"),
    ("DOW", "^DJI", "Dow 30", "USD"),
    ("RUSSELL", "^RUT", "Russell 2000", "USD"),
    ("USDBRL", "BRL=X", "Dólar", "BRL"),
)

INDEX_PROVIDER_SYMBOLS = tuple(provider for _, provider, _, _ in INDEX_UNIVERSE)


class UniverseRegistry:
    """Canonical website preload; quote failures never remove identities."""

    version = "mission68.v1"

    def __init__(self) -> None:
        self.universes = PUBLIC_UNIVERSES

    def get_universe(self, name: str) -> list[str]:
        aliases = {"b3_core": "B3", "b3_extended": "B3", "bdr": "BDR", "crypto": "Crypto", "us": "USA"}
        return list(self.universes.get(aliases.get(name, name), ()))

    def get_all_assets(self) -> list[str]:
        return [symbol for category in self.universes.values() for symbol in category]

    def _item(self, symbol: str, category: str) -> dict[str, Any]:
        exchange = "BMFBOVESPA" if category in {"B3", "BDR"} else "BINANCE" if category == "Crypto" else US_EXCHANGE_BY_SYMBOL.get(symbol)
        return {
            "symbol": symbol,
            "label": symbol,
            "category": category,
            "market": category,
            "exchange": exchange,
            "provider_symbol": provider_symbol(symbol),
        }

    def get_public_payload(self) -> dict[str, Any]:
        items = [self._item(symbol, category) for category, symbols in self.universes.items() for symbol in symbols]
        payload = {
            "version": self.version,
            "items": items,
            "counts": {category: len(symbols) for category, symbols in self.universes.items()},
            "total": len(items),
        }
        return copy.deepcopy(payload)


universe_registry = UniverseRegistry()
