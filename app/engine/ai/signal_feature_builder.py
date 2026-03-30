# =====================================================
# SIGNAL FEATURE BUILDER
# =====================================================

import numpy as np


def build_features(signals):

    features = []

    for s in signals:

        features.append([
            s.get("momentum", 0),
            s.get("volatility", 0),
            s.get("volume_spike", 0),
            s.get("trend", 0)
        ])

    return np.array(features)