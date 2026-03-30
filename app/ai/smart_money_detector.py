# =====================================================
# STOCKNEWSBR SMART MONEY DETECTOR
# Fast + Safe
# =====================================================

def detect_smart_money(df):

    try:

        if df is None or len(df) < 20:
            return False

        if "Volume" not in df or "Open" not in df or "Close" not in df:
            return False

        volume = df["Volume"]

        avg_volume = volume.rolling(20).mean().iloc[-1]
        last_volume = volume.iloc[-1]

        price_move = df["Close"].iloc[-1] - df["Open"].iloc[-1]

        if avg_volume and last_volume > avg_volume * 2 and price_move > 0:
            return True

        return False

    except Exception:

        return False