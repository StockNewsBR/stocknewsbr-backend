# =====================================================
# RANKING SERVICE
# Fast + Crash Safe
# =====================================================

from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, Depends

from app.cache.market_data_cache import get_market_data
from app.cache.snapshot_cache import get_snapshot_info, get_snapshot_signals
from app.config import SYMBOLS
from app.dependencies import require_active_plan
from app.system.system_metrics import current_provider_call_source

logger = logging.getLogger("stocknewsbr.ranking")

router = APIRouter(
    prefix="/ranking",
    tags=["Ranking"],
)

CACHE_TTL = 120
SNAPSHOT_MAX_AGE = 600
ALLOW_NETWORK_FALLBACK = str(
    os.getenv("RANKING_ALLOW_NETWORK_FALLBACK", "0")
).strip().lower() in {"1", "true", "yes", "on"}

_RANK_CACHE = {
    "data": [],
    "timestamp": 0.0,
    "snapshot_signature": "",
}


def calculate_rsi(series: pd.Series, period: int = 14):
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_ema(series: pd.Series, period: int):
    return series.ewm(span=period, adjust=False).mean()


def calculate_macd(series: pd.Series):
    ema12 = calculate_ema(series, 12)
    ema26 = calculate_ema(series, 26)

    macd = ema12 - ema26
    signal = calculate_ema(macd, 9)

    return macd, signal


def calculate_score(symbol: str, df: pd.DataFrame):
    try:
        if df is None or df.empty:
            return None

        close = df["Close"]

        rsi_series = calculate_rsi(close)

        if rsi_series.dropna().empty:
            return None

        rsi = float(rsi_series.dropna().iloc[-1])

        macd, macd_signal = calculate_macd(close)

        if macd.dropna().empty:
            return None

        macd_value = float(macd.dropna().iloc[-1])
        macd_signal_value = float(macd_signal.dropna().iloc[-1])

        ema9 = float(calculate_ema(close, 9).iloc[-1])
        ema21 = float(calculate_ema(close, 21).iloc[-1])

        score = 0

        if rsi < 30:
            score += 25
        elif rsi < 50:
            score += 15
        elif rsi > 70:
            score -= 10

        if macd_value > macd_signal_value:
            score += 25
        else:
            score -= 10

        if ema9 > ema21:
            score += 25
            trend = "UPTREND"
        else:
            score -= 10
            trend = "DOWNTREND"

        if "Volume" in df.columns and len(df) > 20:
            volume_mean = df["Volume"].rolling(20).mean().iloc[-1]
            last_volume = df["Volume"].iloc[-1]

            if last_volume > volume_mean:
                score += 25

        return {
            "symbol": symbol,
            "score": max(score, 0),
            "trend": trend,
            "rsi": round(rsi, 2),
            "breakout": ema9 > ema21,
        }

    except Exception as exc:
        logger.warning("Score error %s: %s", symbol, exc)
        return None


def fetch_market_data():
    try:
        return get_market_data(SYMBOLS)
    except Exception as exc:
        logger.error("Market download error: %s", exc)
        return None


def _normalize_snapshot_ranking(snapshot_info: dict | None = None):
    snapshot_info = snapshot_info or get_snapshot_info()
    signal_count = int(snapshot_info.get("signals", 0) or 0)
    age_seconds = snapshot_info.get("age_seconds")

    if signal_count <= 0:
        return []

    if age_seconds is not None and age_seconds > SNAPSHOT_MAX_AGE:
        return []

    results = []

    for row in get_snapshot_signals():
        if not isinstance(row, dict):
            continue

        symbol = row.get("ticker") or row.get("symbol")

        if not symbol:
            continue

        try:
            score = float(row.get("score", 0) or 0)
        except Exception:
            score = 0.0

        results.append(
            {
                "symbol": symbol,
                "score": score,
                "trend": row.get("trend"),
                "rsi": row.get("rsi"),
                "breakout": bool(row.get("breakout", False)),
                "price": row.get("price"),
            }
        )

    results.sort(key=lambda item: item["score"], reverse=True)
    return results


def _snapshot_signature(snapshot_info: dict) -> str:
    timestamp = (
        snapshot_info.get("timestamp")
        or snapshot_info.get("updated_at")
        or snapshot_info.get("generated_at")
        or snapshot_info.get("last_good_timestamp")
    )
    signals = int(snapshot_info.get("signals", 0) or 0)
    has_signals = bool(snapshot_info.get("has_signals"))
    is_empty = bool(snapshot_info.get("is_empty"))
    return f"{timestamp}|{signals}|{int(has_signals)}|{int(is_empty)}"


def _get_symbol_frame(data, symbol):
    if data is None:
        return None

    columns = getattr(data, "columns", None)

    if columns is None:
        return None

    if hasattr(columns, "levels"):
        available = set(columns.get_level_values(0))

        if symbol not in available:
            return None

        return data[symbol]

    if len(SYMBOLS) == 1 and symbol == SYMBOLS[0]:
        return data

    return None


def generate_ranking(force_refresh: bool = False):
    now = time.time()
    snapshot_info = get_snapshot_info()
    snapshot_signature = _snapshot_signature(snapshot_info)

    if (
        not force_refresh
        and _RANK_CACHE["data"]
        and _RANK_CACHE.get("snapshot_signature") == snapshot_signature
        and now - _RANK_CACHE["timestamp"] < CACHE_TTL
    ):
        return list(_RANK_CACHE["data"])

    snapshot_results = _normalize_snapshot_ranking(snapshot_info)

    if snapshot_results:
        _RANK_CACHE["data"] = list(snapshot_results)
        _RANK_CACHE["timestamp"] = now
        _RANK_CACHE["snapshot_signature"] = snapshot_signature
        return list(snapshot_results)

    if not ALLOW_NETWORK_FALLBACK or current_provider_call_source() == "http":
        _RANK_CACHE["data"] = []
        _RANK_CACHE["timestamp"] = now
        _RANK_CACHE["snapshot_signature"] = snapshot_signature
        return []

    data = fetch_market_data()

    if data is None:
        _RANK_CACHE["data"] = []
        _RANK_CACHE["timestamp"] = now
        _RANK_CACHE["snapshot_signature"] = snapshot_signature
        return []

    results = []

    for symbol in SYMBOLS:
        try:
            frame = _get_symbol_frame(data, symbol)
            score = calculate_score(symbol, frame)

            if score:
                results.append(score)
        except Exception:
            continue

    results.sort(key=lambda row: row["score"], reverse=True)

    _RANK_CACHE["data"] = list(results)
    _RANK_CACHE["timestamp"] = now
    _RANK_CACHE["snapshot_signature"] = snapshot_signature

    return results


def get_ranking(force_refresh: bool = False):
    return generate_ranking(force_refresh=force_refresh)


def get_top_ranking(min_score: int = 50, limit: int = 10):
    ranking = get_ranking()
    return [row for row in ranking if row["score"] >= min_score][:limit]


def get_top_movers(limit: int = 10):
    return [row["symbol"] for row in get_ranking()[:limit]]


@router.get("")
def ranking_endpoint(current_user=Depends(require_active_plan)):
    del current_user
    return {"data": get_ranking()}


@router.get("/top")
def top_endpoint(min_score: int = 50, current_user=Depends(require_active_plan)):
    del current_user
    return {"data": get_top_ranking(min_score=min_score)}
