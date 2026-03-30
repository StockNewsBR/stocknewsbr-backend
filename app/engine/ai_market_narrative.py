class MarketNarrativeEngine:

    def generate(self, signals):

        if not signals:
            return ""

        narrative = []

        tech = []
        momentum = []
        liquidity = []
        volume = []

        for s in signals:

            ticker = s.get("ticker")

            if not ticker:
                continue

            if s.get("sector") == "technology":
                tech.append(ticker)

            if s.get("momentum", 0) > 6:
                momentum.append(ticker)

            if s.get("liquidity_sweep", 0) > 1:
                liquidity.append(ticker)

            if s.get("volume_spike", 0) > 2:
                volume.append(ticker)

        if tech:
            narrative.append(
                f"Technology stocks leading momentum: {', '.join(tech[:3])}"
            )

        if liquidity:
            narrative.append(
                f"Liquidity sweep detected in {', '.join(liquidity[:3])}"
            )

        if volume:
            narrative.append(
                f"Unusual volume activity in {', '.join(volume[:3])}"
            )

        if momentum:
            narrative.append(
                f"Strong momentum detected in {', '.join(momentum[:3])}"
            )

        return "\n".join(narrative)