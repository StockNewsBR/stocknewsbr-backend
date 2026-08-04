"""Mission 34 — Benchmark do backtest engine (Achado 34-01).

Mede ``replay_trading_scenario`` com dataset sintetico de seed fixa e captura
um digest do resultado completo para provar equivalencia funcional
antes/depois de otimizacoes.

Uso:
    python scripts/mission_34_benchmark_backtest.py --label baseline --sizes 100,500,1000
    python scripts/mission_34_benchmark_backtest.py --label after --sizes 100,500,1000

Regras da missao: sem rede, sem producao, seed fixa, saida estruturada,
fail-fast se a extrapolacao quadratica do proximo tamanho exceder o limite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.portfolio.backtest_engine import replay_trading_scenario  # noqa: E402

MAX_PROJECTED_SECONDS = 600.0


def make_ohlc(n: int, seed: int = 34) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    price = 100.0
    for i in range(n):
        drift = rng.gauss(0.02, 0.6)
        open_price = price
        close = max(1.0, open_price + drift)
        high = max(open_price, close) + abs(rng.gauss(0, 0.3))
        low = max(0.5, min(open_price, close) - abs(rng.gauss(0, 0.3)))
        volume = abs(rng.gauss(1_000_000, 250_000)) + 1_000
        rows.append(
            {
                "time": f"t{i:06d}",
                "open": round(open_price, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "volume": round(volume, 2),
            }
        )
        price = close
    return rows


def digest(result: dict) -> str:
    payload = json.dumps(result, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def bench_size(n: int, reps: int, measure_memory: bool) -> dict:
    rows = make_ohlc(n)
    times: list[float] = []
    result = None
    for _ in range(reps):
        start = time.perf_counter()
        result = replay_trading_scenario("TEST34", rows)
        times.append(time.perf_counter() - start)

    entry: dict = {
        "n": n,
        "reps": reps,
        "times_s": [round(t, 4) for t in times],
        "median_s": round(statistics.median(times), 4),
        "digest": digest(result),
        "trades": len(result.get("trades", [])),
        "events": len(result.get("events", [])),
        "bars_used": result.get("data_quality", {}).get("bars_used"),
    }

    if measure_memory:
        tracemalloc.start()
        replay_trading_scenario("TEST34", rows)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        entry["tracemalloc_peak_mb"] = round(peak / (1024 * 1024), 2)

    return entry


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("deve ser >= 1")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--sizes", default="100,500,1000")
    parser.add_argument("--reps", type=_positive_int, default=3)
    parser.add_argument("--memory", action="store_true")
    args = parser.parse_args()

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    report = {
        "label": args.label,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "seed": 34,
        "results": [],
        "skipped": [],
    }

    # warmup: importa pandas e aquece caminhos de codigo fora da medicao
    bench_size(60, 1, False)

    last = None
    for n in sizes:
        if last is not None and last["median_s"] > 0:
            projected = last["median_s"] * (n / last["n"]) ** 2
            if projected > MAX_PROJECTED_SECONDS:
                report["skipped"].append(
                    {"n": n, "projected_s": round(projected, 1), "reason": "fail_fast_quadratic_projection"}
                )
                print(f"SKIP n={n}: projecao quadratica {projected:.0f}s > {MAX_PROJECTED_SECONDS:.0f}s")
                continue
        reps = args.reps if n <= 1000 else 1
        entry = bench_size(n, reps, args.memory)
        report["results"].append(entry)
        last = entry
        print(
            f"n={n} median={entry['median_s']}s times={entry['times_s']} "
            f"trades={entry['trades']} events={entry['events']} digest={entry['digest'][:12]}"
        )

    out_dir = ROOT / "runtime" / "mission_34" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"backtest_{args.label}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"WROTE {out_path}")


if __name__ == "__main__":
    main()
