# =====================================================
# STOCKNEWSBR LIQUIDITY TRAP DETECTOR
# Fast + Crash Safe
# =====================================================

def detect_liquidity_trap(df):

    try:

        if df is None or len(df) < 20:
            return False

        if "Low" not in df or "Close" not in df:
            return False

        low = df["Low"]
        close = df["Close"]

        support = low.rolling(20).min().iloc[-2]

        break_support = low.iloc[-1] < support
        recover = close.iloc[-1] > support

        return break_support and recover

    except Exception:

        return False