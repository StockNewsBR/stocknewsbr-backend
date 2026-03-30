# =====================================================
# AI MARKET STORY ENGINE
# =====================================================

class MarketStoryEngine:

    def generate(self, signals, regime=None, sectors=None):

        if not signals:
            return "Market activity currently quiet."

        story = []

        top = signals[:5]

        tickers = [s.get("ticker") for s in top if s.get("ticker")]

        if tickers:
            story.append(
                f"Top market activity detected in {', '.join(tickers[:3])}."
            )

        momentum = [
            s["ticker"] for s in signals
            if s.get("momentum", 0) > 6
        ]

        if momentum:
            story.append(
                f"Strong momentum detected in {', '.join(momentum[:3])}."
            )

        liquidity = [
            s["ticker"] for s in signals
            if s.get("liquidity_sweep", 0) > 1
        ]

        if liquidity:
            story.append(
                f"Liquidity sweeps appearing in {', '.join(liquidity[:3])}."
            )

        volume = [
            s["ticker"] for s in signals
            if s.get("volume_spike", 0) > 2
        ]

        if volume:
            story.append(
                f"Unusual volume activity detected in {', '.join(volume[:3])}."
            )

        if regime:
            story.append(
                f"Current market regime classified as {regime}."
            )

        if sectors:
            strongest = sectors[0]["sector"]
            story.append(
                f"Sector rotation currently favoring {strongest}."
            )

        return "\n".join(story)