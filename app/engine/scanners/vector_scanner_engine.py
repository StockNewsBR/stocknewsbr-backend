# =====================================================
# VECTOR SCANNER ENGINE (V36)
# =====================================================

import logging

from app.engine.scanners.breakout_scanner import breakout_scan
from app.engine.scanners.momentum_scanner import momentum_scan
from app.engine.scanners.liquidity_scanner import liquidity_scan
from app.engine.scanners.smart_money_scanner import smart_money_scan
from app.engine.scanners.top_movers import top_movers_scan

logger = logging.getLogger("stocknewsbr.engine.vector_scanner")


class VectorScannerEngine:

    def __init__(self):

        self.scanners = [
            breakout_scan,
            momentum_scan,
            liquidity_scan,
            smart_money_scan,
            top_movers_scan
        ]

    def run(self, features, matrices):

        try:

            signals = []

            for scanner in self.scanners:

                result = scanner(features, matrices)

                if result:
                    signals.extend(result)

            return signals

        except Exception as e:

            logger.error(f"Vector scanner error: {e}")

            return []


# global instance
vector_scanner_engine = VectorScannerEngine()