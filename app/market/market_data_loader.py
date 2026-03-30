# =====================================================
# MARKET DATA LOADER
# =====================================================

import logging
from typing import List, Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger("stocknewsbr.market_data_loader")


def _normalize_symbol(symbol: str) -> str:
    symbol = (symbol or "").upper().strip()

    if not symbol:
        return symbol

    if (
        "." not in symbol
        and "-" not in symbol
        and symbol.endswith(("3", "4", "5", "6", "11", "34"))
    ):
        return f"{symbol}.SA"

    return symbol


def _normalize_ticker_display(symbol: str, normalized_symbol: str) -> str:
    original = (symbol or "").upper().strip()

    if original:
        return original

    return normalized_symbol.replace(".SA", "")


def batch_download(
    tickers: List[str],
    period: str = "1d",
    interval: str = "5m",
) -> Optional[pd.DataFrame]:
    try:
        if not tickers or not isinstance(tickers, (list, tuple)):
            return None

        normalized = [_normalize_symbol(ticker) for ticker in tickers if ticker]

        if not normalized:
            return None

        data = yf.download(
            tickers=list(normalized),
            period=period,
            interval=interval,
            group_by="ticker",
            threads=True,
            auto_adjust=True,
            progress=False,
            prepost=True,
        )

        if data is None or data.empty:
            return None

        try:
            if hasattr(data.index, "tz") and data.index.tz is not None:
                data.index = data.index.tz_convert("UTC")
            else:
                data.index = data.index.tz_localize("UTC")
        except Exception:
            logger.warning("Timezone normalization failed")

        return data
    except Exception as exc:
        logger.error("Batch download error: %s", exc)
        return None


def _extract_single_ticker_frame(data: Optional[pd.DataFrame], symbol: str) -> Optional[pd.DataFrame]:
    if data is None or data.empty:
        return None

    normalized_symbol = _normalize_symbol(symbol)
    columns = getattr(data, "columns", None)

    if columns is None:
        return None

    if hasattr(columns, "levels"):
        available = set(columns.get_level_values(0))

        if normalized_symbol not in available:
            return None

        frame = data[normalized_symbol].copy()
    else:
        frame = data.copy()

    return frame if frame is not None and not frame.empty else None


def get_ticker_frame(
    symbol: str,
    period: str = "1d",
    interval: str = "5m",
) -> Optional[pd.DataFrame]:
    normalized_symbol = _normalize_symbol(symbol)
    data = batch_download([normalized_symbol], period=period, interval=interval)
    return _extract_single_ticker_frame(data, normalized_symbol)


def get_chart_data(symbol: str, interval: str = "1D"):
    interval_map = {
        "1D": ("1d", "5m"),
        "1W": ("5d", "30m"),
        "1M": ("1mo", "1d"),
    }

    period, yf_interval = interval_map.get(str(interval or "1D").upper(), ("1d", "5m"))
    frame = get_ticker_frame(symbol, period=period, interval=yf_interval)

    if frame is None or frame.empty:
        return []

    rows = []

    for index, row in frame.tail(240).iterrows():
        rows.append(
            {
                "time": str(index),
                "open": float(row.get("Open", 0) or 0),
                "high": float(row.get("High", 0) or 0),
                "low": float(row.get("Low", 0) or 0),
                "close": float(row.get("Close", 0) or 0),
                "volume": float(row.get("Volume", 0) or 0),
            }
        )

    return rows


def get_price_snapshot(symbol: str):
    frame = get_ticker_frame(symbol, period="5d", interval="30m")

    if frame is None or frame.empty:
        return None

    try:
        last = frame.iloc[-1]
        previous = frame.iloc[-2] if len(frame) > 1 else last
        last_close = float(last.get("Close", 0) or 0)
        previous_close = float(previous.get("Close", last_close) or last_close)
        change = last_close - previous_close
        change_pct = 0.0 if previous_close == 0 else (change / previous_close) * 100

        return {
            "symbol": _normalize_ticker_display(symbol, _normalize_symbol(symbol)),
            "price": round(last_close, 4),
            "change": round(change, 4),
            "change_pct": round(change_pct, 4),
            "after_hours": None,
            "pre_market": None,
            "volume": float(last.get("Volume", 0) or 0),
            "high": float(last.get("High", 0) or 0),
            "low": float(last.get("Low", 0) or 0),
        }
    except Exception as exc:
        logger.error("Price snapshot error for %s: %s", symbol, exc)
        return None
