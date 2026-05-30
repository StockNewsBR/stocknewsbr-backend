# =====================================================
# STOCKNEWSBR BACKTEST ENGINE
# Fast lightweight simulation
# =====================================================

import logging
import yfinance as yf
import pandas as pd

logger = logging.getLogger("stocknewsbr.backtest")


# =====================================================
# BACKTEST PORTFOLIO
# =====================================================

def backtest_portfolio(tickers):

    if not tickers:
        return {}

    try:

        # ---------------------------------------------
        # DOWNLOAD DATA
        # ---------------------------------------------

        data = yf.download(

            tickers=tickers,

            period="1y",

            interval="1d",

            auto_adjust=True,

            progress=False,

            threads=False,

            timeout=8

        )

        if data is None or data.empty:
            return {}

        # ---------------------------------------------
        # HANDLE SINGLE TICKER STRUCTURE
        # ---------------------------------------------

        if isinstance(data.columns, pd.MultiIndex):

            close = data["Close"]

        else:

            # single ticker case
            close = pd.DataFrame({tickers[0]: data["Close"]})

        # ---------------------------------------------
        # CALCULATE PERFORMANCE
        # ---------------------------------------------

        performance = {}

        for ticker in close.columns:

            try:

                series = close[ticker].dropna()

                if len(series) < 2:
                    continue

                start = series.iloc[0]
                end = series.iloc[-1]

                pct = ((end - start) / start) * 100

                performance[ticker] = round(pct, 2)

            except Exception as e:

                logger.warning(f"Backtest error {ticker}: {e}")

                continue

        return performance

    except Exception as e:

        logger.error(f"Backtest engine failure: {e}")

        return {}
