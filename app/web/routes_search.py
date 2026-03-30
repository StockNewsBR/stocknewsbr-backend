# =====================================================
# STOCKNEWSBR SEARCH ROUTES
# =====================================================

import re

from fastapi import APIRouter, Depends
import logging

from app.dependencies import require_channel_access
from app.watchlists.watchlist_default import (
    WATCHLIST_B3,
    WATCHLIST_US_GLOBAL,
    WATCHLIST_BDR,
    WATCHLIST_CRYPTO
)

router = APIRouter(
    prefix="/web",
    tags=["web"],
    dependencies=[Depends(require_channel_access("web"))],
)

logger = logging.getLogger("stocknewsbr.web.search")


ALL_TICKERS = set(
    WATCHLIST_B3 +
    WATCHLIST_US_GLOBAL +
    WATCHLIST_BDR +
    WATCHLIST_CRYPTO
)

B3_PATTERN = re.compile(r"^[A-Z]{4}(?:3|4|5|6|11)$")
BDR_PATTERN = re.compile(r"^[A-Z]{4,5}34$")
USA_PATTERN = re.compile(r"^[A-Z]{1,5}$")
CRYPTO_PATTERN = re.compile(r"^[A-Z]{2,10}USD$")
CRYPTO_BASES = {
    "BTC",
    "ETH",
    "BNB",
    "SOL",
    "XRP",
    "ADA",
    "DOGE",
    "MATIC",
    "AVAX",
    "LINK",
}


def _normalize_query(value: str) -> str:
    return str(value or "").upper().strip().replace(" ", "").replace(".SA", "").replace("-USD", "USD")


def _synthetic_candidates(query: str) -> list[str]:
    normalized = _normalize_query(query)

    if not normalized:
        return []

    candidates: list[str] = []

    if B3_PATTERN.fullmatch(normalized):
        candidates.append(normalized)

    if BDR_PATTERN.fullmatch(normalized):
        candidates.append(normalized)

    if USA_PATTERN.fullmatch(normalized):
        candidates.append(normalized)

    if CRYPTO_PATTERN.fullmatch(normalized):
        candidates.append(normalized)

    if normalized in CRYPTO_BASES:
        candidates.append(f"{normalized}USD")

    seen: set[str] = set()
    ordered: list[str] = []

    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)

    return ordered


@router.get("/search/{query}")
def search_ticker(query: str):

    try:
        normalized = _normalize_query(query)

        results = [
            ticker
            for ticker in ALL_TICKERS
            if normalized in _normalize_query(ticker)
        ]

        combined: list[str] = []
        seen: set[str] = set()

        for ticker in [*_synthetic_candidates(normalized), *results]:
            clean = _normalize_query(ticker)

            if not clean or clean in seen:
                continue

            seen.add(clean)
            combined.append(clean)

        return combined[:20]

    except Exception as e:

        logger.error(f"Search error: {e}")

        return []
