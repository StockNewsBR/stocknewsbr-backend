import pytest
import pandas as pd
import numpy as np
from app.engine.matrix.market_matrix_builder import build_market_matrices

def test_build_market_matrices_valid():
    pool = {
        "AAPL": pd.DataFrame({"Close": np.random.rand(15), "Volume": np.random.rand(15)}),
        "MSFT": pd.DataFrame({"Close": np.random.rand(20), "Volume": np.random.rand(20)}),
        "GOOG": pd.DataFrame({"Close": np.random.rand(12), "Volume": np.random.rand(12)}),
    }
    result = build_market_matrices(pool)
    assert result is not None
    assert result["tickers"] == ["AAPL", "MSFT", "GOOG"]
    assert result["price_matrix"].shape == (3, 12)
    assert result["volume_matrix"].shape == (3, 12)
    # The last elements should be retained, verify MSFT
    assert np.allclose(result["price_matrix"][1], pool["MSFT"]["Close"].values[-12:])

def test_build_market_matrices_empty_pool():
    pool = {}
    result = build_market_matrices(pool)
    assert result is None

def test_build_market_matrices_missing_columns():
    pool = {
        "AAPL": pd.DataFrame({"Close": np.random.rand(15)}), # missing Volume
        "MSFT": pd.DataFrame({"Volume": np.random.rand(20)}), # missing Close
        "GOOG": pd.DataFrame({"Close": np.random.rand(12), "Volume": np.random.rand(12)}),
    }
    result = build_market_matrices(pool)
    assert result is not None
    # AAPL and MSFT skipped in matrices, but tickers list contains all original keys
    assert result["tickers"] == ["AAPL", "MSFT", "GOOG"]
    assert result["price_matrix"].shape == (1, 12)

def test_build_market_matrices_length_zero():
    pool = {
        "AAPL": pd.DataFrame({"Close": [], "Volume": []}),
        "MSFT": pd.DataFrame({"Close": np.random.rand(15), "Volume": np.random.rand(15)})
    }
    result = build_market_matrices(pool)
    assert result is not None
    # AAPL skipped in matrices, but tickers list contains all original keys
    assert result["tickers"] == ["AAPL", "MSFT"]
    assert result["price_matrix"].shape == (1, 15)

def test_build_market_matrices_not_enough_data():
    pool = {
        "AAPL": pd.DataFrame({"Close": np.random.rand(9), "Volume": np.random.rand(9)}),
    }
    result = build_market_matrices(pool)
    assert result is None
