import re

with open("app/engine/trend_breakout_signal_engine.py", "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    line = line.replace('evaluator.chart_regime_state if "chart_regime_state" in locals() else "unknown"', 'evaluator.chart_regime_state or "unknown"')
    line = line.replace('evaluator.liquidity_event if "liquidity_event" in locals() else "none"', 'evaluator.liquidity_event or "none"')
    line = line.replace('evaluator.long_confidence if "long_confidence" in locals() else 0.0', 'evaluator.long_confidence')
    line = line.replace('evaluator.short_confidence if "short_confidence" in locals() else 0.0', 'evaluator.short_confidence')
    new_lines.append(line)

with open("app/engine/trend_breakout_signal_engine.py", "w") as f:
    f.writelines(new_lines)
