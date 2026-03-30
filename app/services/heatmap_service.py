def calculate_heatmap_score(price, volume):
    if price > 0 and volume > 0:
        return (price * volume) / 100
    return 0