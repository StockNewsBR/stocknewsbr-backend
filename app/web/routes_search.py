# =====================================================
# STOCKNEWSBR SEARCH ROUTES
# =====================================================

import re

from fastapi import APIRouter, Depends
import logging

from app.dependencies import require_channel_access
from app.services.symbol_registry import CRYPTO_BASES, canonical_symbol, has_us_market_qualifier
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
def _normalize_query(value: str) -> str:
    return canonical_symbol(value) or str(value or "").upper().strip().replace(" ", "").replace(".SA", "").replace("-USD", "USD")


def _is_unqualified_crypto_base_query(query: str) -> bool:
    normalized = _normalize_query(query)
    return normalized in CRYPTO_BASES and not has_us_market_qualifier(query)


def _synthetic_candidates(query: str) -> list[str]:
    normalized = _normalize_query(query)

    if not normalized:
        return []

    if _is_unqualified_crypto_base_query(query):
        return []

    candidates: list[str] = []

    if B3_PATTERN.fullmatch(normalized):
        candidates.append(normalized)

    if BDR_PATTERN.fullmatch(normalized) and canonical_symbol(normalized):
        candidates.append(normalized)

    if USA_PATTERN.fullmatch(normalized):
        candidates.append(normalized)

    if CRYPTO_PATTERN.fullmatch(normalized):
        candidates.append(normalized)

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
        if not normalized:
            return []
        if _is_unqualified_crypto_base_query(query):
            return []
        qualified_crypto_base = normalized in CRYPTO_BASES

        results = [] if qualified_crypto_base else [
            ticker
            for ticker in ALL_TICKERS
            if normalized in _normalize_query(ticker)
        ]

        combined: list[str] = []
        seen: set[str] = set()

        for ticker in [*_synthetic_candidates(query), *results]:
            clean = canonical_symbol(ticker) or _normalize_query(ticker)

            if not clean or clean in seen:
                continue

            seen.add(clean)
            combined.append(clean)

        return combined[:20]

    except Exception as e:

        logger.error("Search error: %s", e)

        return []
