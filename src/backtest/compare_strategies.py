"""
compare_strategies.py

Avellaneda-Stoikov market maker vs. a fixed-spread (symmetric) baseline.

Both strategies use the SAME spread formula, parameters, position limits and fees.
The only difference:
  - AS:       quotes around the inventory-adjusted reservation price
  - Baseline: the quote formula ignores inventory -> quotes centered on the mid
              (position limits and fees still apply to the baseline's real inventory)
So any difference in results comes from the inventory adjustment.

Each session runs on the same random seed for both strategies (same fair-value path).

Run from the src/ directory:
    python backtest/compare_strategies.py
    python backtest/compare_strategies.py --sessions 300 --ticks 2000
"""
import argparse
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_session import MarketSession  # noqa: E402


class BaselineSession(MarketSession):
    """
    Same session, same rules (position limits, fees, order sizes all use the REAL inventory).
    Only difference: the quote formula is told inventory = 0, so quotes stay centered on the
    mid price instead of the inventory-adjusted reservation price.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        original_refresh = self.market_maker.refresh

        def refresh_ignoring_inventory(*r_args, **r_kwargs):
            if "inventory" in r_kwargs:
                r_kwargs["inventory"] = 0
            elif len(r_args) >= 2:
                r_args = (r_args[0], 0, *r_args[2:])
            return original_refresh(*r_args, **r_kwargs)

        self.market_maker.refresh = refresh_ignoring_inventory


def run_session(session_cls, seed: int, ticks: int) -> dict:
    s = session_cls(seed=seed)
    s.market_maker.total_ticks = ticks
    s.configure(live=True)
    s.start_strategy()
    path = []
    for _ in range(ticks):
        s.advance(1)
        path.append(s.inventory)
    snap = s.portfolio_snapshot()
    return {
        "pnl": snap["pnl"],
        "final_inv": snap["inventory"],
        "inv_std": st.pstdev(path),
        "max_abs_inv": max(abs(x) for x in path),
    }


def summarize(name: str, rows: list[dict]) -> dict:
    pnl = [r["pnl"] for r in rows]
    out = {
        "strategy": name,
        "mean_pnl": st.mean(pnl),
        "pnl_std": st.pstdev(pnl),
        "sharpe_like": st.mean(pnl) / st.pstdev(pnl) if st.pstdev(pnl) else float("nan"),
        "mean_inv_std": st.mean(r["inv_std"] for r in rows),
        "mean_max_abs_inv": st.mean(r["max_abs_inv"] for r in rows),
        "mean_abs_final_inv": st.mean(abs(r["final_inv"]) for r in rows),
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=200)
    ap.add_argument("--ticks", type=int, default=2000)
    args = ap.parse_args()

    as_rows, base_rows = [], []
    for seed in range(args.sessions):
        as_rows.append(run_session(MarketSession, seed, args.ticks))
        base_rows.append(run_session(BaselineSession, seed, args.ticks))

    a, b = summarize("Avellaneda-Stoikov", as_rows), summarize("Fixed-spread baseline", base_rows)
    print(f"{args.sessions} sessions x {args.ticks} ticks\n")
    keys = ["mean_pnl", "pnl_std", "sharpe_like", "mean_inv_std", "mean_max_abs_inv", "mean_abs_final_inv"]
    print(f"{'metric':<22}{'AS':>14}{'baseline':>14}{'change':>10}")
    for k in keys:
        chg = (a[k] - b[k]) / abs(b[k]) * 100 if b[k] else float("nan")
        print(f"{k:<22}{a[k]:>14,.2f}{b[k]:>14,.2f}{chg:>9.1f}%")


if __name__ == "__main__":
    main()
