# =====================================================
# STOCKNEWSBR FAKE BREAKOUT DETECTOR
# Fast + Crash Safe
# =====================================================

def detect_fake_breakout(df):

    try:

        if df is None or len(df) < 20:
            return False

        if "High" not in df or "Close" not in df:
            return False

        high = df["High"]
        close = df["Close"]

        resistance = high.rolling(20).max().iloc[-2]

        if resistance is None:
            return False

        breakout = high.iloc[-1] > resistance
        close_back = close.iloc[-1] < resistance

        return breakout and close_back

    except Exception:

        return False