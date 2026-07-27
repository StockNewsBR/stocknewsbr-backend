import math
import pytest

from app.services import public_market_data_service as pmds

@pytest.fixture
def mock_dependencies(monkeypatch):
    monkeypatch.setattr(pmds, "INDEX_UNIVERSE", [
        ("^BVSP", "^BVSP", "Ibovespa", "BRL"),
        ("AAPL34", "AAPL34", "Apple BDR", "BRL")
    ])

    cache = {}
    sparks = {}
    aliases = {
        "^BVSP": ["^BVSP", "IBOV"],
        "AAPL34": ["AAPL34.SA", "AAPL34"],
        "IBOV": ["IBOV", "^BVSP"],
        "BOVA11": ["BOVA11.SA", "BOVA11"]
    }

    def _cached_price_payloads(symbols, allow_stale=False):
        found = {}
        for s in symbols:
            if s in cache:
                found[s] = cache[s]
        return found

    def _load_public_chart_rows(syms, interval, scope=None):
        for s in syms:
            if s in sparks:
                return sparks[s]
        return []

    def _symbol_aliases(sym):
        return aliases.get(sym, [sym])

    monkeypatch.setattr(pmds, "cached_price_payloads", _cached_price_payloads)
    monkeypatch.setattr(pmds, "load_public_chart_rows", _load_public_chart_rows)
    monkeypatch.setattr(pmds, "_symbol_aliases", _symbol_aliases)

    class Mocks:
        pass

    m = Mocks()
    m.cache = cache
    m.sparks = sparks
    m.aliases = aliases
    return m


def test_1_quote_direto_tem_prioridade(mock_dependencies):
    mock_dependencies.cache["^BVSP"] = {
        "price": 120000.0,
        "change": 500.0,
        "change_pct": 0.42,
        "previous_close": 119500.0,
        "quote_time": 1234567890
    }
    mock_dependencies.sparks["^BVSP"] = [{"close": 100000.0}, {"close": 100000.0}]

    res = pmds.build_public_indices_payload()["items"]
    ibov = next(r for r in res if r["symbol"] == "^BVSP")

    assert ibov["price"] == 120000.0
    assert ibov["change"] == 500.0
    assert ibov["change_pct"] == 0.42
    assert ibov["previous_close"] == 119500.0


def test_2_alias_correto(mock_dependencies, monkeypatch):
    monkeypatch.setattr(pmds, "INDEX_UNIVERSE", [
        ("IBOV", "^BVSP", "Ibovespa", "BRL")
    ])
    mock_dependencies.cache["IBOV"] = {"price": 120000.0}

    res = pmds.build_public_indices_payload()["items"]
    ibov = res[0]

    assert ibov["symbol"] == "IBOV"
    assert ibov["price"] == 120000.0


def test_3_alias_incorreto_nao_casa(mock_dependencies, monkeypatch):
    monkeypatch.setattr(pmds, "INDEX_UNIVERSE", [
        ("IBOV", "^BVSP", "Ibovespa", "BRL")
    ])
    mock_dependencies.cache["^BVSP_SOMETHING"] = {"price": 99999.0}
    mock_dependencies.cache["IBOV2"] = {"price": 88888.0}

    res = pmds.build_public_indices_payload()["items"]
    ibov = res[0]

    assert ibov["price"] is None


def test_4_fallback_de_price(mock_dependencies):
    mock_dependencies.cache["^BVSP"] = {
        "quote_time": 1000,
        "market_state": "CLOSED",
    }
    mock_dependencies.sparks["^BVSP"] = [
        {"close": 110000.0},
        {"close": 115000.0}
    ]

    res = pmds.build_public_indices_payload()["items"]
    ibov = next(r for r in res if r["symbol"] == "^BVSP")

    assert ibov["price"] == 115000.0
    assert ibov["previous_close"] == 110000.0
    assert ibov["change"] == 5000.0
    assert ibov["change_pct"] == 4.55


def test_5_variacao_negativa(mock_dependencies):
    mock_dependencies.sparks["^BVSP"] = [
        {"close": 100.0},
        {"close": 90.0}
    ]

    res = pmds.build_public_indices_payload()["items"]
    ibov = next(r for r in res if r["symbol"] == "^BVSP")

    assert ibov["price"] == 90.0
    assert ibov["change"] == -10.0
    assert ibov["change_pct"] == -10.0


def test_6_apenas_um_ponto(mock_dependencies):
    mock_dependencies.sparks["^BVSP"] = [
        {"close": 115000.0}
    ]

    res = pmds.build_public_indices_payload()["items"]
    ibov = next(r for r in res if r["symbol"] == "^BVSP")

    assert ibov["price"] == 115000.0
    assert ibov["previous_close"] is None
    assert ibov["change"] is None
    assert ibov["change_pct"] is None


def test_7_zero(mock_dependencies, monkeypatch):
    mock_dependencies.sparks["^BVSP"] = []
    # Mocking _valid_chart_closes to bypass _finite_positive removing 0
    monkeypatch.setattr(pmds, "_valid_chart_closes", lambda rows: [0.0, 100.0])

    res = pmds.build_public_indices_payload()["items"]
    ibov = next(r for r in res if r["symbol"] == "^BVSP")

    assert ibov["price"] == 100.0
    assert ibov["previous_close"] == 0.0
    assert ibov["change"] is None
    assert ibov["change_pct"] is None


def test_8_nan_e_inf(mock_dependencies, monkeypatch):
    mock_dependencies.cache["^BVSP"] = {
        "price": float("nan"),
        "change": float("inf"),
        "change_pct": float("-inf"),
        "previous_close": float("nan")
    }

    monkeypatch.setattr(pmds, "_valid_chart_closes", lambda rows: [float("nan"), float("inf"), float("-inf"), 100.0])

    res = pmds.build_public_indices_payload()["items"]
    ibov = next(r for r in res if r["symbol"] == "^BVSP")

    assert ibov["price"] == 100.0
    assert ibov["previous_close"] is None or not math.isnan(ibov["previous_close"])
    assert ibov["change"] is None or not math.isnan(ibov["change"])
    assert ibov["change_pct"] is None or not math.isnan(ibov["change_pct"])


def test_9_valores_nao_numericos(mock_dependencies, monkeypatch):
    mock_dependencies.cache["^BVSP"] = {
        "price": None,
        "change": "",
        "change_pct": [],
        "previous_close": {}
    }

    # We bypass _valid_chart_closes filtering to force bad values if possible,
    # or just use the cache bad values. Since cache bad values are filtered by _finite_positive.
    res = pmds.build_public_indices_payload()["items"]
    ibov = next(r for r in res if r["symbol"] == "^BVSP")

    assert ibov["price"] is None
    assert ibov["change"] is None
    assert ibov["change_pct"] is None
    assert ibov["previous_close"] is None


def test_10_freshness_honesta(mock_dependencies):
    mock_dependencies.cache["^BVSP"] = {
        "quote_time": 1000,
        "market_state": "CLOSED"
    }
    mock_dependencies.sparks["^BVSP"] = [{"close": 100.0}, {"close": 110.0}]

    res = pmds.build_public_indices_payload()["items"]
    ibov = next(r for r in res if r["symbol"] == "^BVSP")

    assert ibov["quote_time"] == 1000
    assert ibov["market_state"] == "CLOSED"
    assert ibov["status"] == "valid"
    assert "source" not in ibov or ibov["source"] != "real-time"


def test_11_bdr(mock_dependencies, monkeypatch):
    monkeypatch.setattr(pmds, "INDEX_UNIVERSE", [
        ("AAPL34", "AAPL34", "Apple BDR", "BRL")
    ])
    mock_dependencies.cache["AAPL"] = {"price": 150.0}

    res = pmds.build_public_indices_payload()["items"]
    aapl34 = res[0]

    assert aapl34["price"] is None


def test_12_indices_distintos(mock_dependencies, monkeypatch):
    monkeypatch.setattr(pmds, "INDEX_UNIVERSE", [
        ("BOVA11", "BOVA11", "BOVA11 ETF", "BRL")
    ])
    mock_dependencies.cache["IBOV"] = {"price": 120000.0}

    res = pmds.build_public_indices_payload()["items"]
    bova11 = res[0]

    assert bova11["price"] is None


def test_13_ordem_e_quantidade(mock_dependencies, monkeypatch):
    universe = [
        ("IDX1", "IDX1", "Index 1", "BRL"),
        ("IDX2", "IDX2", "Index 2", "BRL"),
        ("IDX3", "IDX3", "Index 3", "USD")
    ]
    monkeypatch.setattr(pmds, "INDEX_UNIVERSE", universe)
    mock_dependencies.aliases["IDX1"] = ["IDX1", "I1"]
    mock_dependencies.aliases["IDX2"] = ["IDX2", "I2"]
    mock_dependencies.aliases["IDX3"] = ["IDX3", "I3"]

    res = pmds.build_public_indices_payload()["items"]

    assert len(res) == 3
    assert [r["symbol"] for r in res] == ["IDX1", "IDX2", "IDX3"]
