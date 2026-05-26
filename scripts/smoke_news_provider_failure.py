from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.public_news_service import build_public_news_payload


def main() -> None:
    symbol = "PETR4"
    with (
        patch("app.services.public_news_service.get_symbol_news", return_value=[]),
        patch("app.services.public_news_service.get_news_cached_report", return_value={"status": "empty"}),
        patch(
            "app.services.public_news_service.get_news_cache_info",
            return_value={
                "status": "cold",
                "provider": "smoke",
                "provider_status": "error",
                "provider_error": "forced smoke provider failure",
            },
        ),
    ):
        payload = build_public_news_payload(symbol, limit=6, source="smoke_etapa7")

    assert payload["symbol"] == symbol
    assert payload["count"] == 0
    assert payload["status"] == "provider_error"
    assert payload["scope"]["type"] == "ticker"
    assert payload["scope"]["mixed_ticker_allowed"] is False
    assert "forced smoke provider failure" in payload["message"]
    print(json.dumps({"ok": True, "status": payload["status"], "symbol": payload["symbol"], "message": payload["message"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
