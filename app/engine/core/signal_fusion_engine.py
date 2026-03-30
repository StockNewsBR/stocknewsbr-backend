# =====================================================
# STOCKNEWSBR SIGNAL FUSION ENGINE
# =====================================================

import logging
from typing import List, Dict

from app.engine.scanners.momentum_scanner import scan_momentum
from app.engine.scanners.breakout_scanner import scan_breakouts
from app.engine.scanners.liquidity_scanner import scan_liquidity
from app.engine.scanners.smart_money_scanner import scan_smart_money

logger = logging.getLogger("stocknewsbr.engine.signal_fusion")


# =====================================================
# CONFIG
# =====================================================

FUSION_LIMIT = 40


# =====================================================
# SAFE DICT
# =====================================================

def _ensure_symbol(asset):

    if not isinstance(asset, dict):
        return None

    return asset.get("symbol")


# =====================================================
# MERGE SIGNALS
# =====================================================

def _merge_signals(*lists):

    merged = {}

    try:

        for signal_list in lists:

            for asset in signal_list:

                symbol = _ensure_symbol(asset)

                if not symbol:
                    continue

                if symbol not in merged:
                    merged[symbol] = {
                        "symbol": symbol,
                        "score": 0,
                        "signals": 0
                    }

                merged[symbol]["signals"] += 1

                merged[symbol]["score"] += 1

        return list(merged.values())

    except Exception as e:

        logger.error(f"Signal merge error: {e}")

        return []


# =====================================================
# SIGNAL FUSION
# =====================================================

def run_signal_fusion(snapshot: List[Dict]):

    if not snapshot:
        return []

    try:

        momentum = scan_momentum(snapshot)

        breakout = scan_breakouts(snapshot)

        liquidity = scan_liquidity(snapshot)

        smart_money = scan_smart_money(snapshot)

        merged = _merge_signals(
            momentum,
            breakout,
            liquidity,
            smart_money
        )

        merged.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return merged[:FUSION_LIMIT]

    except Exception as e:

        logger.error(f"Signal fusion error: {e}")

        return []