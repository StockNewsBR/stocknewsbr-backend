# =====================================================
# ADAPTIVE AI SIGNAL ENGINE
# =====================================================

import numpy as np
import logging

logger = logging.getLogger("stocknewsbr.engine.ai")

_weights = np.array([0.25, 0.25, 0.25, 0.25])


def compute_adaptive_scores(features):

    try:

        scores = features @ _weights

        return scores

    except Exception as e:

        logger.error(f"AI scoring error: {e}")

        return None


def update_weights(new_weights):

    global _weights

    if len(new_weights) == len(_weights):

        _weights = np.array(new_weights)