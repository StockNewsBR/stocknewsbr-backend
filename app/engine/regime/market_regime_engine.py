# =====================================================
# STOCKNEWSBR MARKET REGIME ENGINE
# =====================================================

import logging
import numpy as np

logger = logging.getLogger("stocknewsbr.engine.regime")


# =====================================================
# CONFIG
# =====================================================

TREND_THRESHOLD = 0.015
VOLATILITY_THRESHOLD = 0.03


# =====================================================
# REGIME ENUM
# =====================================================

REGIME_TREND = "TRENDING"
REGIME_SIDEWAYS = "SIDEWAYS"
REGIME_VOLATILE = "VOLATILE"
REGIME_RISK_OFF = "RISK_OFF"


# =====================================================
# DETECT REGIME
# =====================================================

def detect_market_regime(price_matrix):

    try:

        if price_matrix is None:
            return REGIME_SIDEWAYS

        returns = np.diff(price_matrix) / price_matrix[:, :-1]

        market_return = np.nanmean(returns[:, -20:])
        market_vol = np.nanstd(returns[:, -20:])

        if market_vol > VOLATILITY_THRESHOLD:

            return REGIME_VOLATILE

        if market_return < -TREND_THRESHOLD:

            return REGIME_RISK_OFF

        if abs(market_return) > TREND_THRESHOLD:

            return REGIME_TREND

        return REGIME_SIDEWAYS

    except Exception as e:

        logger.exception("Regime detection failed: %s", e)

        return REGIME_SIDEWAYS