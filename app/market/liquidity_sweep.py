def detect_liquidity_sweep(df: pd.DataFrame):

    try:

        if df is None or len(df) < 3:
            return None

        df = df.dropna()

        required = {"High", "Low", "Close"}

        if not required.issubset(df.columns):
            return None

        high = df["High"]
        low = df["Low"]
        close = df["Close"]

        last_high = high.iloc[-1]
        prev_high = high.iloc[-2]

        last_low = low.iloc[-1]
        prev_low = low.iloc[-2]

        last_close = close.iloc[-1]

        if last_high > prev_high and last_close < prev_high:

            return {"event": "LIQUIDITY_SWEEP", "direction": "DOWN"}

        if last_low < prev_low and last_close > prev_low:

            return {"event": "LIQUIDITY_SWEEP", "direction": "UP"}

    except Exception as e:

        logger.error(f"Liquidity sweep error: {e}")

    return None