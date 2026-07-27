## Plan to fix code health issue in `app/engine/trend_breakout_signal_engine.py`

**Issue**: The `build_trend_breakout_payload` function is nearly 900 lines long and handles far too many responsibilities (calculating loop variables, trend checks, volatility checks, breakouts, signal scoring, position management, and creating the final payload). This creates a massive block of code that is hard to read, maintain, and test individually.

**Strategy**: Extract cohesive logic blocks out of the giant `build_trend_breakout_payload` into separate, well-named helper functions, focusing heavily on extracting the core of the `for` loop body without changing behavior.

1. **Extract state initialization:** Extract initialization of variables before the loop to a helper like `_initialize_state`.
2. **Extract bar statistics calculation:** Extract loop-level variables for indicators, bodies, spreads, wicks, into a helper function `_calculate_bar_metrics` or similar, reducing the number of variables in the loop scope.
3. **Extract trend and volatility checks:** Extract conditions for `long_trend`, `short_trend`, `volatility_ok`, `price_expansion` etc. into `_evaluate_trend_and_volatility`.
4. **Extract breakout conditions:** Extract `long_breakout`, `short_breakout`, `resistance_reclaim_long`, etc., into a helper function like `_evaluate_breakout_conditions`.
5. **Extract pullbacks and reversal conditions:** Extract logic for `long_pullback`, `short_pullback`, etc., into another helper function.
6. **Consolidate signal scoring and execution:** Move signal evaluation (BUY, SHORT) and position management (stop loss, take profit) into smaller helper functions.

*Wait*, pulling everything into helper functions right now might be very error-prone if we don't have passing tests or can't easily isolate the state changes. The function makes heavy use of localized state mutated across loop iterations:
- `current_position`
- `entry_index`, `entry_price`
- `best_price_after_entry`, `worst_price_after_entry`
- `last_exit_index`
- `latest_signal`, `latest_score`, `latest_coherence` etc.

A safer and common approach to refactoring such a massive procedural loop is to extract a class: a "SignalProcessor" or similar, which holds this state and provides methods for each step.

Let's look closely at `build_trend_breakout_payload`:
```python
def build_trend_breakout_payload(...):
    # Setup ...
    df = _build_indicator_frame(...)

    # State initialization ...
    events = []
    current_position = None
    ...

    for index in range(len(df)):
       # process bar ...
       # update state ...
       # append events ...

    # Final payload creation ...
    return payload
```

We can move the whole `for` loop and the state variables into a helper class, say `_TrendBreakoutEvaluator` or `_TrendBreakoutState`.
This limits the scope of variables and makes it much easier to extract logic into smaller methods.

Let's examine how many tests cover this code. We've seen 14 tests in `tests/test_trend_breakout_signal_engine.py`. They pass if I use a virtual environment, but the sandbox environment was complaining about missing `pandas`. Let me first set up `pandas` correctly so tests can run, and then iteratively extract logic.
