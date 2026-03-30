from collections import defaultdict


class SectorRotationEngine:

    def analyze(self, signals):

        sectors = defaultdict(float)
        counts = defaultdict(int)

        for s in signals:

            sector = s.get("sector")

            if not sector:
                continue

            sectors[sector] += s.get("score", 0)
            counts[sector] += 1

        ranking = []

        for sector in sectors:

            avg = sectors[sector] / counts[sector]

            ranking.append({
                "sector": sector,
                "strength": round(avg, 2)
            })

        ranking.sort(
            key=lambda x: x["strength"],
            reverse=True
        )

        return ranking