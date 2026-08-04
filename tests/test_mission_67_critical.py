import pandas as pd

from app.Frontend.trader_terminal import get_terminal
from app.engine.matrix.market_matrix_builder import build_market_matrices
from app.web.routes_workspace import router


def test_market_matrix_returns_only_tickers_in_matrix():
    valid = pd.DataFrame({"Close": range(10), "Volume": range(10)})
    result = build_market_matrices({"INVALID": pd.DataFrame(), "PETR4": valid})

    assert result is not None
    assert result["tickers"] == ["PETR4"]
    assert result["price_matrix"].shape == (1, 10)


def test_terminal_preserves_main_window_null_and_reuses_room_socket():
    html = get_terminal()

    assert "const FOCUSED_TAB = null;" in html
    assert "ROOM_SOCKET_TICKER === ACTIVE_TICKER" in html
    assert "ROOM_SOCKET.readyState === WebSocket.CONNECTING" in html

    popout_html = get_terminal(focused_tab="grafico")
    assert 'const FOCUSED_TAB = "grafico";' in popout_html


def test_help_center_videos_route_precedes_dynamic_slug():
    paths = [route.path for route in router.routes]

    assert paths.index("/web/help-center/videos") < paths.index("/web/help-center/{slug}")
