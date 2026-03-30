# =====================================================
# STOCKNEWSBR TREND ACCELERATION
# Fast + Safe
# =====================================================

def detect_trend_acceleration(df):

    try:

        if df is None or len(df) < 30:
            return False

        if "Close" not in df:
            return False

        close = df["Close"]

        ema_fast = close.ewm(span=9).mean()
        ema_slow = close.ewm(span=21).mean()

        if ema_fast.iloc[-1] > ema_slow.iloc[-1] and ema_fast.iloc[-2] <= ema_slow.iloc[-2]:
            return True

        return False

    except Exception:

        return False