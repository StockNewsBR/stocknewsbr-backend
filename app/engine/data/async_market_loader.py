# =====================================================
# ASYNC MARKET LOADER
# =====================================================

import asyncio
import logging
import yfinance as yf

logger = logging.getLogger("stocknewsbr.market.loader")


async def fetch_symbol(symbol):

    try:

        loop = asyncio.get_running_loop()

        df = await loop.run_in_executor(
            None,
            lambda: yf.download(
                symbol,
                period="5d",
                interval="5m",
                progress=False
            )
        )

        return symbol, df

    except Exception as e:

        logger.warning(f"Download error {symbol}: {e}")

        return symbol, None


async def load_symbols(symbols):

    tasks = [fetch_symbol(s) for s in symbols]

    results = await asyncio.gather(*tasks)

    pool = {}

    for symbol, df in results:

        if df is not None and len(df) > 50:
            pool[symbol] = df

    return pool