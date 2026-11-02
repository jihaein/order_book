"""
benchmark_engine.py

Throughput test for the matching engine: sends 200,000 random orders
(80% limit, 20% market) and reports orders/sec. Fixed seed -> same order mix every run.

Run from the src/ directory:
    python backtest/benchmark_engine.py
"""
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from matching import MatchingEngine, Side  # noqa: E402

N_ORDERS = 200_000
RUNS = 3


def run_once(seed: int = 7) -> tuple[float, int]:
    rng = random.Random(seed)
    engine = MatchingEngine()
    fills = 0
    start = time.perf_counter()
    for _ in range(N_ORDERS):
        side = Side.BID if rng.random() < 0.5 else Side.ASK
        if rng.random() < 0.8:
            offset = rng.randint(-2, 20) * 0.05
            price = 100 - offset if side is Side.BID else 100 + offset
            report = engine.place_limit(side, round(price, 2), rng.randint(1, 10))
        else:
            report = engine.place_market(side, rng.randint(1, 10))
        fills += len(report.fills)
    elapsed = time.perf_counter() - start
    return N_ORDERS / elapsed, fills


if __name__ == "__main__":
    print(f"Python {sys.version.split()[0]}  |  {N_ORDERS:,} orders x {RUNS} runs\n")
    rates = []
    for i in range(RUNS):
        rate, fills = run_once()
        rates.append(rate)
        print(f"run {i + 1}: {rate:,.0f} orders/sec  ({1e6 / rate:.1f} us/order, {fills:,} fills)")
    print(f"\nmedian: {sorted(rates)[RUNS // 2]:,.0f} orders/sec")
