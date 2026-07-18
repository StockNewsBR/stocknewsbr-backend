import unittest
from unittest.mock import patch

from app.api import routes_public_market
from app.services import public_ai_tools_service


def _tools():
    return public_ai_tools_service._empty_tools()


def _row(
    ticker="PETR4",
    *,
    tool="risk",
    timeframe="1D",
    decision_ready=True,
    can_trade=True,
    audit_status="APPROVED",
):
    return {
        "ticker": ticker,
        "symbol": ticker,
        "tool": tool,
        "score": 88.0,
        "score_source_scale": "0_100",
        "master_score": 88.0,
        "master_score_raw": 88.0,
        "master_score_source_scale": "0_100",
        "timeframe": timeframe,
        "signal": "BUY",
        "trade_action": "BUY",
        "decision_state": "BUY_READY",
        "decision_ready": decision_ready,
        "can_trade": can_trade,
        "audit_status": audit_status,
        "blocked_by_auditor": audit_status == "BLOCKED",
        "price": 37.5,
        "volume": 1_000_000,
        "data_quality": "real_time",
        "market_data_updated_at": "2026-07-14T12:00:00+00:00",
        "decision_envelope": {
            "decision_status": "READY" if decision_ready else "BLOCKED",
            "decision_ready": decision_ready,
        },
    }


def _snapshot(tools, *, stale=False):
    symbol_rows = {}
    for rows in tools.values():
        for row in rows:
            symbol = str(row.get("ticker") or row.get("symbol"))
            current = symbol_rows.get(symbol)
            if current is None or (current.get("decision_ready") is not True and row.get("decision_ready") is True):
                symbol_rows[symbol] = dict(row)
    return {
        "ai_tools": tools,
        "symbol_snapshots": symbol_rows,
        "generated_at": "2026-07-14T12:00:00+00:00",
        "source": "engine",
        "stale": stale,
    }


class Mission68PublicAiToolsTests(unittest.TestCase):
    def test_filters_by_canonical_symbol_tool_and_declared_timeframe(self):
        tools = _tools()
        tools["risk"] = [
            _row("PETR4", timeframe="1D"),
            _row("PETR4", timeframe="1W"),
            _row("VALE3", timeframe="1D"),
        ]
        tools["flow"] = [_row("PETR4", tool="flow", timeframe="1D", decision_ready=False, can_trade=False)]

        with patch.object(public_ai_tools_service, "get_snapshot", return_value=_snapshot(tools)):
            payload = public_ai_tools_service.build_public_ai_tools_payload(
                symbol="PETR4.SA",
                tool="risk",
                timeframe="1d",
            )

        self.assertEqual(payload["status"], "READY")
        self.assertEqual(payload["reason"], "qualified_findings_available")
        self.assertEqual(payload["symbol"], "PETR4")
        self.assertEqual(payload["tool"], "risk")
        self.assertEqual(payload["timeframe"], "1D")
        self.assertEqual(payload["displayable_count"], 1)
        self.assertEqual(payload["actionable_count"], 1)
        self.assertEqual(payload["tools"]["risk"][0]["ticker"], "PETR4")
        self.assertTrue(payload["tools"]["risk"][0]["actionable"])
        self.assertFalse(payload["tools"]["flow"])
        self.assertTrue(payload["analyzed_at"])

    def test_valid_empty_current_snapshot_does_not_restore_old_findings(self):
        old_tools = _tools()
        old_tools["risk"] = [_row()]
        with patch.object(public_ai_tools_service, "get_snapshot", return_value=_snapshot(_tools())), patch.object(
            public_ai_tools_service, "get_last_good_snapshot", return_value=_snapshot(old_tools),
        ):
            payload = public_ai_tools_service.build_public_ai_tools_payload(tool="risk")

        self.assertEqual(payload["status"], "NO_QUALIFIED_FINDING")
        self.assertEqual(payload["reason"], "no_qualified_finding")
        self.assertEqual(payload["source"], "snapshot")
        self.assertFalse(payload["using_fallback"])
        self.assertEqual(payload["displayable_count"], 0)
        self.assertEqual(payload["actionable_count"], 0)
        self.assertFalse(payload["tools"]["risk"])

    def test_missing_timeframe_is_not_presented_as_requested_timeframe(self):
        tools = _tools()
        row = _row()
        row.pop("timeframe")
        tools["risk"] = [row]
        with patch.object(public_ai_tools_service, "get_snapshot", return_value=_snapshot(tools)):
            payload = public_ai_tools_service.build_public_ai_tools_payload(symbol="PETR4", tool="risk", timeframe="1D")

        self.assertEqual(payload["status"], "NO_QUALIFIED_FINDING")
        self.assertEqual(payload["displayable_count"], 0)
        self.assertFalse(payload["tools"]["risk"])

    def test_auditor_or_can_trade_block_keeps_context_but_never_actionable(self):
        tools = _tools()
        tools["risk"] = [_row(audit_status="BLOCKED")]
        with patch.object(public_ai_tools_service, "get_snapshot", return_value=_snapshot(tools)):
            payload = public_ai_tools_service.build_public_ai_tools_payload(tool="risk")

        row = payload["tools"]["risk"][0]
        self.assertEqual(payload["status"], "READY")
        self.assertEqual(payload["displayable_count"], 1)
        self.assertEqual(payload["actionable_count"], 0)
        self.assertFalse(row["actionable"])
        self.assertFalse(row["decision_ready"])
        self.assertFalse(row["can_trade"])

    def test_last_good_fallback_is_explicitly_stale_and_non_actionable(self):
        fallback_tools = _tools()
        fallback_tools["risk"] = [_row()]
        with patch.object(public_ai_tools_service, "get_snapshot", return_value={"ai_tools": {}, "source": "empty"}), patch.object(
            public_ai_tools_service, "get_last_good_snapshot", return_value=_snapshot(fallback_tools),
        ):
            payload = public_ai_tools_service.build_public_ai_tools_payload(tool="risk")

        row = payload["tools"]["risk"][0]
        self.assertEqual(payload["status"], "STALE_DATA")
        self.assertEqual(payload["reason"], "last_good_snapshot_fallback")
        self.assertEqual(payload["source"], "last_good_snapshot")
        self.assertTrue(payload["using_fallback"])
        self.assertEqual(payload["displayable_count"], 1)
        self.assertEqual(payload["actionable_count"], 0)
        self.assertFalse(row["actionable"])
        self.assertFalse(row["decision_ready"])
        self.assertFalse(row["can_trade"])

    def test_unavailable_snapshot_has_explicit_status_instead_of_silent_zero(self):
        with patch.object(public_ai_tools_service, "get_snapshot", return_value={"ai_tools": {}, "source": "empty"}), patch.object(
            public_ai_tools_service, "get_last_good_snapshot", return_value={},
        ):
            payload = public_ai_tools_service.build_public_ai_tools_payload()

        self.assertEqual(payload["status"], "SNAPSHOT_UNAVAILABLE")
        self.assertEqual(payload["reason"], "snapshot_unavailable")
        self.assertEqual(payload["displayable_count"], 0)
        self.assertEqual(payload["actionable_count"], 0)
        self.assertTrue(payload["analyzed_at"])

    def test_ai_kill_switch_returns_structured_block_without_reading_snapshot(self):
        with patch.object(public_ai_tools_service, "is_ai_decisions_disabled", return_value=True), patch.object(
            public_ai_tools_service, "get_snapshot",
        ) as get_snapshot:
            payload = public_ai_tools_service.build_public_ai_tools_payload(symbol="PETR4", tool="risk")

        get_snapshot.assert_not_called()
        self.assertEqual(payload["status"], "KILL_SWITCHED")
        self.assertEqual(payload["reason"], "kill_switch=DISABLE_AI_DECISIONS")
        self.assertEqual(payload["displayable_count"], 0)
        self.assertEqual(payload["actionable_count"], 0)
        self.assertFalse(any(payload["tools"].values()))

    def test_snapshot_read_error_is_structured_and_logged_not_silent_zero(self):
        with patch.object(public_ai_tools_service, "get_snapshot", side_effect=RuntimeError("cache unavailable")), patch.object(
            public_ai_tools_service, "get_last_good_snapshot", return_value={},
        ):
            payload = public_ai_tools_service.build_public_ai_tools_payload()

        self.assertEqual(payload["status"], "ERROR")
        self.assertEqual(payload["reason"], "snapshot_read_error:RuntimeError")
        self.assertEqual(payload["displayable_count"], 0)
        self.assertEqual(payload["actionable_count"], 0)

    def test_public_endpoint_forwards_optional_filters(self):
        with patch.object(
            routes_public_market,
            "build_public_ai_tools_payload",
            return_value={"status": "NO_QUALIFIED_FINDING", "tools": _tools()},
        ) as build_payload:
            payload = routes_public_market.public_ai_tools(symbol="petr4.sa", tool="risk", timeframe="1d")

        self.assertEqual(payload["status"], "NO_QUALIFIED_FINDING")
        build_payload.assert_called_once_with(symbol="petr4.sa", tool="risk", timeframe="1d")


if __name__ == "__main__":
    unittest.main()
