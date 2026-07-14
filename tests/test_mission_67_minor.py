import math

import numpy as np
import pandas as pd
import pytest

from app.ai.ai_confluence import calculate_confluence
from app.ai.market_narrative import generate_market_narrative
from app.ai.signal_ranker import rank_signals
from app.ai.signal_strength import calculate_signal_strength
from app.ai.vector_signal_engine import volatility
from app.engine.ai.signal_feature_builder import build_features
from app.engine.ai_opportunity_engine import OpportunityEngine
from app.engine.engine_vector_features import compute_vector_features
from app.engine.events.fake_breakout import detect_fake_breakout


def test_non_finite_ai_inputs_are_normalized(monkeypatch):
    assert calculate_confluence(math.nan, 10)["percentage"] == 0
    assert calculate_confluence(20, 10)["percentage"] == 100
    assert rank_signals([{"change": math.inf}, {"change": 2}])[0]["change"] == 2
    assert calculate_signal_strength(math.nan, {"percentage": math.inf})["strength"] == 0


def test_market_narrative_preserves_each_explicit_value(monkeypatch):
    monkeypatch.setattr("app.ai.market_narrative.get_snapshot_signals", lambda: [])
    monkeypatch.setattr("app.ai.market_narrative.generate_market_heatmap", lambda rows: {"global": {"market_strength": 77}})
    monkeypatch.setattr("app.ai.market_narrative._generate_market_narrative", lambda symbol, score, confluence: (score, confluence))

    assert generate_market_narrative(score=12, confluence=None) == (12, 0)
    assert generate_market_narrative(score=None, confluence=3) == (77, 3)


def test_zero_mean_volatility_and_empty_feature_shape():
    assert volatility([-1.0, 1.0]) == 1.0
    assert build_features([]).shape == (0, 4)


def test_opportunity_limit_rejects_negative():
    with pytest.raises(ValueError, match="non-negative"):
        OpportunityEngine().detect([{"score": 1}], limit=-1)


def test_vector_features_skip_non_finite_and_zero_denominator():
    valid = pd.DataFrame({"Close": np.arange(1.0, 31.0), "Volume": np.ones(30)})
    zero = valid.copy()
    zero.loc[5, "Close"] = 0
    infinite = valid.copy()
    infinite.loc[5, "Close"] = math.inf

    assert [row["ticker"] for row in compute_vector_features({"OK": valid, "ZERO": zero, "INF": infinite})] == ["OK"]


def test_fake_breakout_requires_full_previous_window():
    short = pd.DataFrame({"High": [1] * 19 + [2], "Close": [1] * 20})
    assert detect_fake_breakout(short) is False
