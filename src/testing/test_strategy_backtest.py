import sys
import math
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from strategy_backtest import MarketDataRow, run_backtest


def row(last: float, bid: float, ask: float, bid_qty: int, ask_qty: int, theoretical: float):
    return MarketDataRow("t", last, bid, ask, bid_qty, ask_qty, theoretical)


def test_three_fair_values_are_available() -> None:
    item = row(100, 99, 101, 30, 10, 100.25)
    assert item.fair_value("mid") == 100
    assert item.fair_value("micro") == 100.5
    assert item.fair_value("theoretical") == 100.25


def test_backtest_applies_fee_and_inventory_limit() -> None:
    rows = [
        row(100, 99, 101, 10, 10, 100),
        row(98, 98, 99, 10, 10, 98.5),
        row(97, 97, 98, 10, 10, 97.5),
    ]
    result = run_backtest(
        rows,
        "mid",
        quote_quantity=10,
        inventory_limit=10,
        fee_rate=0.00003,
    )
    assert result.max_abs_inventory <= 10
    assert result.fees_paid > 0


def test_backtest_reports_krw_using_contract_multiplier() -> None:
    rows = [
        row(100, 99, 101, 10, 10, 100),
        row(98, 98, 99, 10, 10, 98.5),
    ]
    unit_result = run_backtest(
        rows,
        "mid",
        quote_quantity=1,
        inventory_limit=1,
        fee_rate=0.00003,
        initial_cash=1_000_000_000,
        contract_multiplier=1,
    )
    result = run_backtest(
        rows,
        "mid",
        quote_quantity=1,
        inventory_limit=1,
        fee_rate=0.00003,
        initial_cash=1_000_000_000,
        contract_multiplier=250_000,
    )
    assert result.traded_quantity == 1
    assert math.isclose(result.fees_paid, unit_result.fees_paid * 250_000)
    assert math.isclose(result.pnl, unit_result.pnl * 250_000, abs_tol=0.01)


if __name__ == "__main__":
    for test in (
        test_three_fair_values_are_available,
        test_backtest_applies_fee_and_inventory_limit,
        test_backtest_reports_krw_using_contract_multiplier,
    ):
        test()
        print(f"PASS: {test.__name__}")
