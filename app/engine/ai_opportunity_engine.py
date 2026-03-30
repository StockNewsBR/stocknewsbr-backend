class OpportunityEngine:

    def detect(self, signals, limit=10):

        if not signals:
            return []

        sorted_signals = sorted(
            signals,
            key=lambda x: x.get("score", 0),
            reverse=True
        )

        return sorted_signals[:limit]