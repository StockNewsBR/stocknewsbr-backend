import math
from app.services.symbol_registry import _row_quality_score, dedupe_canonical_rows, canonical_symbol

def test_1_nan_float():
    row = {
        "canonical_symbol": "TEST",
        "master_score_raw": float("nan"),
        "master_score": float("nan"),
        "score": float("nan"),
    }
    score = _row_quality_score(row)
    assert not any(math.isnan(s) for s in score)
    assert score == (0.0, 0.0, 0.0)

def test_2_infinito_positivo():
    row = {
        "canonical_symbol": "TEST",
        "master_score_raw": float("inf"),
        "master_score": float("inf"),
        "score": float("inf"),
    }
    score = _row_quality_score(row)
    assert not any(math.isinf(s) for s in score)
    assert score == (0.0, 0.0, 0.0)

def test_3_infinito_negativo():
    row = {
        "canonical_symbol": "TEST",
        "master_score_raw": float("-inf"),
        "master_score": float("-inf"),
        "score": float("-inf"),
    }
    score = _row_quality_score(row)
    assert not any(math.isinf(s) for s in score)
    assert score == (0.0, 0.0, 0.0)

def test_4_strings_nao_finitas():
    for val in ["nan", "NaN", "inf", "+inf", "-inf", "Infinity", "-Infinity"]:
        row = {
            "canonical_symbol": "TEST",
            "master_score_raw": val,
            "master_score": val,
            "score": val,
        }
        score = _row_quality_score(row)
        assert score == (0.0, 0.0, 0.0)

def test_5_strings_invalidas():
    for val in ["", "abc", "--", "null"]:
        row = {
            "canonical_symbol": "TEST",
            "master_score_raw": val,
            "master_score": val,
            "score": val,
        }
        score = _row_quality_score(row)
        assert score == (0.0, 0.0, 0.0)

def test_6_none_e_estruturas_invalidas():
    for val in [None, [], {}, object()]:
        row = {
            "canonical_symbol": "TEST",
            "master_score_raw": val,
            "master_score": val,
            "score": val,
        }
        score = _row_quality_score(row)
        assert score == (0.0, 0.0, 0.0)

def test_7_zero_finito():
    for val in [0, 0.0]:
        row = {
            "canonical_symbol": "TEST",
            "master_score_raw": val,
            "master_score": val,
            "score": val,
        }
        score = _row_quality_score(row)
        assert score == (0.0, 0.0, 0.0)

def test_8_numeros_finitos_positivos():
    row = {
        "canonical_symbol": "TEST",
        "master_score_raw": 1.5,
        "master_score": 42.0,
        "score": 100.123,
    }
    assert _row_quality_score(row) == (1.5, 42.0, 100.123)

def test_9_numeros_finitos_negativos():
    row = {
        "canonical_symbol": "TEST",
        "master_score_raw": -1.5,
        "master_score": -42.0,
        "score": -100.123,
    }
    assert _row_quality_score(row) == (-1.5, -42.0, -100.123)

def test_10_linha_valida_vence_linha_nao_finita():
    row_valid = {
        "canonical_symbol": "TEST",
        "master_score_raw": 10.0,
        "master_score": 10.0,
        "score": 10.0,
        "provider_symbol": "VALID"
    }
    row_nan = {
        "canonical_symbol": "TEST",
        "master_score_raw": float("nan"),
        "master_score": float("nan"),
        "score": float("nan"),
        "provider_symbol": "NAN"
    }
    # row_nan vem primeiro, mas row_valid tem score superior (10 > 0)
    result = dedupe_canonical_rows([row_nan, row_valid])
    assert len(result) == 1
    assert result[0]["provider_symbol"] == "VALID"

def test_11_determinismo():
    rows = [
        {"canonical_symbol": "TEST", "score": 5.0, "provider_symbol": "A"},
        {"canonical_symbol": "TEST", "score": 15.0, "provider_symbol": "B"},
        {"canonical_symbol": "TEST", "score": 2.0, "provider_symbol": "C"}
    ]
    res1 = dedupe_canonical_rows(rows)
    res2 = dedupe_canonical_rows(rows)
    assert res1 == res2
    assert res1[0]["provider_symbol"] == "B"

def test_12_nao_mutacao():
    row = {
        "canonical_symbol": "TEST",
        "score": float("nan")
    }
    original_nan = row["score"]
    _row_quality_score(row)
    assert math.isnan(row["score"])
    assert row["score"] is original_nan

def test_13_canonicalizacao_brasileira():
    assert canonical_symbol("PETR4.SA") == "PETR4"
    assert canonical_symbol("petr4.sa") == "PETR4"
    assert canonical_symbol("PETR4") == "PETR4"

def test_14_sem_cross_assignment():
    assert canonical_symbol("AAPL34") != "AAPL"
    assert canonical_symbol("BOVA11") != "IBOV"
    assert canonical_symbol("PETR4") != "VALE3"
    assert canonical_symbol("UNKNOWN123") == "UNKNOWN123"

def test_15_entrada_vazia():
    assert canonical_symbol(None) == ""
    assert canonical_symbol("") == ""
    assert canonical_symbol("   ") == ""
