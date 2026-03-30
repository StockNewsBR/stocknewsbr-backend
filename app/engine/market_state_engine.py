# =====================================================
# MARKET STATE ENGINE
# =====================================================

class MarketStateEngine:

    def __init__(self):

        self.state = {
            "tickers": {},
            "last_update": None
        }


    def update(self, signals):

        if not signals:
            return

        for s in signals:

            ticker = s.get("ticker")

            if not ticker:
                continue

            self.state["tickers"][ticker] = {

                "score": s.get("score"),
                "momentum": s.get("momentum"),
                "volume": s.get("volume_spike"),
                "volatility": s.get("volatility"),
                "liquidity": s.get("liquidity_sweep")

            }


    def get_state(self):

        return self.state