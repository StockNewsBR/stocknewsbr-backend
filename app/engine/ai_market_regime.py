class MarketRegimeEngine:

    def detect(self, signals):

        if not signals:
            return "unknown"

        momentum = 0
        volatility = 0
        liquidity = 0

        for s in signals:

            momentum += s.get("momentum", 0)
            volatility += s.get("volatility", 0)
            liquidity += s.get("liquidity_sweep", 0)

        count = len(signals)

        momentum /= count
        volatility /= count
        liquidity /= count

        if volatility > 4:
            return "high_volatility"

        if momentum > 6:
            return "trending"

        if liquidity > 2:
            return "risk_on"

        return "range"