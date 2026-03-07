def sector_heatmap(signals):

    sectors = {}

    for s in signals:

        sector = s.get("sector","unknown")

        if sector not in sectors:
            sectors[sector] = 0

        sectors[sector] += s["score"]

    return sectors