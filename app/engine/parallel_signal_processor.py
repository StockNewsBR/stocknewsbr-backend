# =====================================================
# PARALLEL SIGNAL PROCESSOR (HIGH PERFORMANCE)
# =====================================================

import logging
import os

from concurrent.futures import ThreadPoolExecutor, as_completed


logger = logging.getLogger("stocknewsbr.parallel")


# =====================================================
# WORKER CONFIG
# =====================================================

CPU_COUNT = os.cpu_count() or 4

MAX_WORKERS = min(32, CPU_COUNT * 2)


# =====================================================
# SINGLE TICKER PROCESS
# =====================================================

def process_single_ticker(ticker, data, signal_function):

    try:

        df = data.get(ticker)

        if df is None:
            return None

        if len(df) < 5:
            return None

        result = signal_function(ticker, df)

        if not result:
            return None

        return result

    except Exception as e:

        logger.debug(f"Signal processing error {ticker}: {e}")

        return None


# =====================================================
# BATCH PROCESS
# =====================================================

def process_batch(tickers, data, signal_function):

    if not tickers:
        return []

    results = []

    try:

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

            futures = [

                executor.submit(
                    process_single_ticker,
                    ticker,
                    data,
                    signal_function
                )

                for ticker in tickers

            ]

            for future in as_completed(futures):

                try:

                    result = future.result()

                    if result is not None:

                        results.append(result)

                except Exception:

                    continue

    except Exception as e:

        logger.error(f"Parallel batch failure: {e}")

        return []

    return results