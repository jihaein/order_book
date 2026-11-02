import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from backtest_rules import QueuePosition, classify_quote, evaluate_quote_fill
from matching import Side


def test_pm_quote_position_rules() -> None:
    assert classify_quote(Side.BID, 100.5, 100.0, 101.0) is QueuePosition.IMPROVING
    assert classify_quote(Side.BID, 100.0, 100.0, 101.0) is QueuePosition.AT_BEST
    assert classify_quote(Side.BID, 99.5, 100.0, 101.0) is QueuePosition.BEHIND
    assert classify_quote(Side.ASK, 100.5, 100.0, 101.0) is QueuePosition.IMPROVING
    assert classify_quote(Side.ASK, 101.0, 100.0, 101.0) is QueuePosition.AT_BEST
    assert classify_quote(Side.ASK, 101.5, 100.0, 101.0) is QueuePosition.BEHIND


def test_passive_quotes_fill_only_after_market_passes() -> None:
    buy = evaluate_quote_fill(Side.BID, 100.0, 100.0, 101.0, 99.95)
    sell = evaluate_quote_fill(Side.ASK, 101.0, 100.0, 101.0, 101.05)
    assert buy.filled and buy.price == 100.0
    assert sell.filled and sell.price == 101.0


def test_marketable_quotes_use_resting_contra_price() -> None:
    buy = evaluate_quote_fill(Side.BID, 200.0, 100.0, 101.0, 101.0)
    sell = evaluate_quote_fill(Side.ASK, 90.0, 100.0, 101.0, 100.0)
    assert buy.price == 101.0
    assert sell.price == 100.0


if __name__ == "__main__":
    for test in (
        test_pm_quote_position_rules,
        test_passive_quotes_fill_only_after_market_passes,
        test_marketable_quotes_use_resting_contra_price,
    ):
        test()
        print(f"PASS: {test.__name__}")
