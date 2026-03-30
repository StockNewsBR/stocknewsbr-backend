# =====================================================
# STOCKNEWSBR VOLUME EXPLOSION
# Fast + Safe
# =====================================================

def detect_volume_explosion(df):

    try:

        if df is None or len(df) < 20:
            return False

        if "Volume" not in df:
            return False

        volume = df["Volume"]

        avg = volume.rolling(20).mean().iloc[-1]
        last = volume.iloc[-1]

        if avg and last > avg * 3:
            return True

        return False

    except Exception:

        return False