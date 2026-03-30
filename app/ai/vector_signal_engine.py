import math
from typing import Iterable, Sequence


def _to_list(values: Iterable[float] | Sequence[float]) -> list[float]:
    return [float(value) for value in values]


def momentum(values: Iterable[float] | Sequence[float]) -> float:
    rows = _to_list(values)

    if len(rows) < 2:
        return 0.0

    previous = rows[-2]

    if previous == 0:
        return 0.0

    return round(((rows[-1] - previous) / previous) * 100, 4)


def volatility(values: Iterable[float] | Sequence[float]) -> float:
    rows = _to_list(values)

    if len(rows) < 2:
        return 0.0

    mean_value = sum(rows) / len(rows)

    if mean_value == 0:
        return 0.0

    variance = sum((row - mean_value) ** 2 for row in rows) / len(rows)
    return round(math.sqrt(variance), 4)


def trend_strength(values: Iterable[float] | Sequence[float]) -> float:
    rows = _to_list(values)

    if len(rows) < 10:
        return 0.0

    short_mean = sum(rows[-5:]) / 5
    long_mean = sum(rows[-10:]) / 10

    if long_mean == 0:
        return 0.0

    return round(((short_mean - long_mean) / long_mean) * 100, 4)
