import pandas as pd

def liquidity_zones(df):

    close = df["Close"]
    volume = df["Volume"]

    vol_ma = volume.rolling(20).mean()

    zones = []

    for i in range(20, len(df)):

        if vol_ma.iloc[i] == 0:
            continue

        vol_ratio = volume.iloc[i] / vol_ma.iloc[i]

        if vol_ratio > 2:

            zones.append({
                "price": float(close.iloc[i]),
                "strength": round(vol_ratio, 2)
            })

    return zones