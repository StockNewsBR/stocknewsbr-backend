class SignalScoringEngine:

    def normalize(self, value, max_value):

        try:

            value = float(value)

        except Exception:
            return 0

        if max_value == 0:
            return 0

        return min(value / max_value, 1)


    def calculate_score(self, signal):

        momentum = self.normalize(signal.get("momentum", 0), 10)

        volume = 1 if signal.get("volume_spike") else 0

        volatility = self.normalize(signal.get("volatility", 0), 5)

        trend = self.normalize(signal.get("trend_strength", 0), 10)

        score = (

            momentum * 0.35 +
            volume * 0.25 +
            volatility * 0.20 +
            trend * 0.20

        )

        return round(score * 100, 2)