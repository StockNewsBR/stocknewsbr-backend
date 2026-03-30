# =====================================================
# MARKET DATA FILTERS
# Fast + Crash Safe
# =====================================================

import logging
import pandas as pd


logger = logging.getLogger("stocknewsbr.market_filters")


def filter_valid_data(df: pd.DataFrame):
    """
    Remove candles inválidos
    """

    try:

        if df is None or not isinstance(df, pd.DataFrame):
            return None

        if len(df) < 5:
            return None

        if "Close" not in df.columns:
            return None

        if df["Close"].isnull().all():
            return None

        return df

    except Exception as e:

        logger.warning(f"Market filter error: {e}")

        return None


def minimum_volume(df: pd.DataFrame, min_volume: int = 100000):
    """
    Filtra ativos com pouco volume
    """

    try:

        if df is None or "Volume" not in df.columns:
            return False

        volume = df["Volume"].iloc[-1]

        if volume is None or pd.isna(volume):
            return False

        return volume >= min_volume

    except Exception as e:

        logger.warning(f"Volume filter error: {e}")

        return False