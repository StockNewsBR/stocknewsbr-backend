import unittest
from unittest.mock import patch

from app.ai.feature_hub import build_ai_tool_payload
from app.engine.market_snapshot_engine import build_snapshot_payload
from app.system import ai_worker


REQUIRED_ALERT_FIELDS = (
    "ticker",
    "detected_at",
    "score",
    "signal",
    "state",
    "trigger",
    "invalidation",
    "invalidacao",
    "metrics",
    "reason",
    "news_context",
)


def _institutional_rows():
    symbols = ["PETR4", "VALE3", "AAPL", "BTCUSD", "BBDC4", "META34", "TSLA", "NVDA", "ITUB4", "ETHUSD", "MSFT", "HAPV3"]
    changes = [1.8, -2.1, 0.4, 2.9, -0.6, 0.2, -1.4, 3.2, 0.1, -0.9, 1.1, -3.0]
    momentum = [1.3, -2.2, 0.8, 3.0, -0.3, 0.1, -1.8, 2.7, 0.0, -0.7, 1.7, -2.5]
    rvol = [1.8, 1.2, 0.9, 2.4, 0.7, 0.5, 1.6, 2.1, 0.6, 1.4, 1.1, 2.8]
    adx = [26, 31, 18, 38, 14, 12, 27, 35, 11, 22, 25, 33]
    atr = [1.6, 2.5, 0.8, 4.2, 0.7, 0.6, 2.2, 2.8, 0.5, 3.1, 1.2, 3.8]
    upper = [0.02, 0.01, 0.04, 0.08, 0.015, 0.03, 0.05, 0.012, 0.01, 0.07, 0.025, 0.09]
    lower = [0.015, 0.05, 0.012, 0.04, 0.02, 0.01, 0.06, 0.018, 0.012, 0.05, 0.02, 0.08]

    rows = []
    for index, symbol in enumerate(symbols):
        price = 30 + index * 7
        change = changes[index]
        rows.append(
            {
                "ticker": symbol,
                "name": symbol,
                "score": 50 + index,
                "price": price,
                "prev_close": price / (1 + change / 100),
                "open": price * (1 - change / 300),
                "high": price * (1 + upper[index]),
                "low": price * (1 - lower[index]),
                "vwap": price * (0.995 if change > 0 else 1.005),
                "volume": int(800_000 * (index + 1) * rvol[index]),
                "avg_volume": int(800_000 * (index + 1)),
                "rsi": 50 + change * 4,
                "adx": adx[index],
                "atr_pct": atr[index],
                "bb_width": 0.02 + atr[index] / 200,
                "kc_width": 0.05,
                "momentum": momentum[index],
                "change_pct": change,
            }
        )
    return rows


class AiInstitutionalBackendTests(unittest.TestCase):
    def test_ai_tools_have_required_institutional_contract_and_distinct_rankings(self):
        rows = _institutional_rows()
        ai_tools = build_ai_tool_payload(rows, rows, limit=20)

        self.assertEqual(
            sorted(ai_tools.keys()),
            [
                "accumulation",
                "breakout_probability",
                "heat_map",
                "institutional_flow",
                "liquidity_map",
                "liquidity_sweep",
                "market_regime",
                "master_score",
                "radar",
                "smart_money",
                "volatility_squeeze",
            ],
        )

        signatures = {}
        for tool, tool_rows in ai_tools.items():
            self.assertTrue(tool_rows, tool)
            for row in tool_rows[:5]:
                for field in REQUIRED_ALERT_FIELDS:
                    self.assertNotIn(row.get(field), (None, "", [], {}), f"{tool}:{field}")
                self.assertEqual(row["invalidacao"], row["invalidation"])
            signatures.setdefault(tuple(row["ticker"] for row in tool_rows[:8]), []).append(tool)

        cloned = [tools for tools in signatures.values() if len(tools) > 1]
        self.assertEqual(cloned, [])
        self.assertIn("component_scores", ai_tools["master_score"][0]["metrics"])
        self.assertIn("weights", ai_tools["master_score"][0]["metrics"])

    def test_worker_generates_ai_tools_each_cycle_and_persists_history(self):
        rows = _institutional_rows()
        generated_snapshot = build_snapshot_payload(rows, source="worker_test", stale=False)

        bootstrap = {
            "primary_launch_platform": "google_app",
            "subscription_unlocks": ["google_app", "website", "telegram"],
        }

        with patch.object(ai_worker, "ensure_runtime_schema"), patch.object(
            ai_worker,
            "get_all_signals",
            return_value=rows,
        ), patch.object(
            ai_worker,
            "get_signal_info",
            return_value={"signals": len(rows), "timestamp": 1_713_866_400.0, "age_seconds": 5},
        ), patch.object(
            ai_worker,
            "get_snapshot_info",
            return_value={"signals": len(rows), "timestamp": 1_713_866_400.0, "age_seconds": 5},
        ), patch.object(
            ai_worker,
            "get_metrics_snapshot",
            return_value={},
        ), patch.object(
            ai_worker,
            "_import_health",
            return_value={"ok": [], "failed": []},
        ), patch.object(
            ai_worker,
            "_snapshot_self_heal",
            return_value={
                "rebuilt_snapshot": False,
                "snapshot_info": {"signals": len(rows), "timestamp": 1_713_866_400.0, "age_seconds": 5, "has_signals": True, "is_empty": False},
                "snapshot": {"signals": rows},
                "source": "current",
                "reason": "reuse_current_snapshot",
                "last_good_snapshot": {},
                "cooldown_remaining_seconds": 0,
            },
        ), patch.object(
            ai_worker,
            "generate_market_snapshot",
            return_value=generated_snapshot,
        ) as generate_snapshot, patch.object(
            ai_worker,
            "persist_ai_alert_history",
            side_effect=lambda value: value,
        ) as persist_history, patch.object(
            ai_worker,
            "update_snapshot",
        ) as update_snapshot, patch.object(
            ai_worker,
            "generate_weekly_polls_for_top_symbols",
            return_value=[],
        ), patch.object(
            ai_worker,
            "run_ai_tab_audit",
            return_value={"overall_status": "ok", "coverage": {}, "available_tools": list(generated_snapshot["ai_tools"].keys()), "benchmark": {}, "batch_summary": {}, "release_decision": {}},
        ), patch.object(
            ai_worker,
            "get_public_bootstrap",
            return_value=bootstrap,
        ), patch.object(
            ai_worker,
            "_write_report",
        ), patch.object(
            ai_worker,
            "_record_report",
        ):
            report = ai_worker.run_ai_worker_cycle()

        generate_snapshot.assert_called_once_with(rows, reuse_last_good_on_empty=True)
        persist_history.assert_called_once()
        update_snapshot.assert_called_once()
        self.assertTrue(report["ai_tools"]["required_fields_ok"])
        self.assertEqual(report["ai_tools"]["tools_ready"], 11)
        self.assertTrue(all(count > 0 for count in report["ai_tools"]["counts"].values()))


if __name__ == "__main__":
    unittest.main()
