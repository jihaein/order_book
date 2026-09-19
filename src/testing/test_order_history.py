"""Small integration checks for MatchingEngine and MarketSession order history.

Run from the project root:

    python test_order_history.py

This uses ordinary ``assert`` statements, so pytest is not required.
"""
import sys
from pathlib import Path


# The test file lives in src/testing, while the application modules live in src.
SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from matching import MatchingEngine, OrderStatus, OrderType, Side
from market_session import MarketSession


def test_matching_engine_lifecycle() -> None:
    """A resting order should remain in history after fills and cancellation."""
    engine = MatchingEngine()

    buy_report = engine.place_limit(
        side=Side.BID,
        price=100.00,
        quantity=10,
        actor="user",
    )
    buy_id = buy_report.order_id

    assert buy_report.status is OrderStatus.RESTING
    assert engine.find(buy_id) is not None, "Resting order should be active"
    assert engine.find_order(buy_id) is not None, "Order should be in history"

    sell_report = engine.place_market(
        side=Side.ASK,
        quantity=4,
        actor="flow",
    )

    historical_buy = engine.find_order(buy_id)
    assert historical_buy is not None
    assert historical_buy.status is OrderStatus.PARTIAL
    assert historical_buy.original_qty == 10
    assert historical_buy.filled_qty == 4
    assert historical_buy.open_qty == 6
    assert engine.find(buy_id) is not None, "Partially filled limit should still rest"

    historical_sell = engine.find_order(sell_report.order_id)
    assert historical_sell is not None
    assert historical_sell.status is OrderStatus.FILLED
    assert historical_sell.filled_qty == 4
    assert historical_sell.open_qty == 0
    assert engine.find(sell_report.order_id) is None, "Market order must not rest"

    removed = engine.pull(buy_id)
    assert removed is not None, "Cancellation should succeed"

    cancelled_buy = engine.find_order(buy_id)
    assert cancelled_buy is not None, "Cancelled order must remain in history"
    assert cancelled_buy.status is OrderStatus.CANCELLED
    assert cancelled_buy.filled_qty == 4
    assert cancelled_buy.open_qty == 6
    assert engine.find(buy_id) is None, "Cancelled order must leave active index"


def test_market_session_keeps_user_history() -> None:
    """MarketSession.my_orders should retain filled and cancelled user IDs."""
    session = MarketSession(seed=123)

    # This deliberately low bid should rest instead of crossing the simulated asks.
    limit_result = session.submit(
        side=Side.BID,
        order_type=OrderType.LIMIT,
        quantity=7,
        price=1.00,
    )

    assert limit_result["outcome"] == "accepted"
    limit_id = limit_result["order_id"]
    assert limit_id in session.my_orders

    initial_rows = session.snapshot()["my_orders"]
    initial_row = next(row for row in initial_rows if row["order_id"] == limit_id)
    assert initial_row["status"] == OrderStatus.RESTING.value
    assert [row["order_id"] for row in session.snapshot()["my_active_orders"]] == [limit_id]
    assert session.snapshot()["my_finished_orders"] == []

    assert session.pull_mine(limit_id) is True
    assert limit_id in session.my_orders, "Cancellation must not erase history ID"

    cancelled_rows = session.snapshot()["my_orders"]
    cancelled_row = next(row for row in cancelled_rows if row["order_id"] == limit_id)
    assert cancelled_row["status"] == OrderStatus.CANCELLED.value
    assert session.snapshot()["my_active_orders"] == []
    assert [row["order_id"] for row in session.snapshot()["my_finished_orders"]] == [limit_id]
    assert session.cancellation_error(limit_id) == "order is already cancelled"

    market_result = session.submit(
        side=Side.BID,
        order_type=OrderType.MARKET,
        quantity=1,
    )

    assert market_result["outcome"] == "accepted"
    market_id = market_result["order_id"]
    assert market_id in session.my_orders, "Market orders must also enter history"

    final_rows = session.snapshot()["my_orders"]
    final_row = next(row for row in final_rows if row["order_id"] == market_id)
    assert final_row["status"] in {
        OrderStatus.FILLED.value,
        OrderStatus.EXPIRED.value,
    }
    assert final_row["order_type"] == OrderType.MARKET.value
    assert "original_quantity" in final_row
    assert "filled_quantity" in final_row
    assert "open_quantity" in final_row


def test_low_sell_limit_returns_acknowledgement() -> None:
    """A low sell price should be collared instead of crashing validation."""
    session = MarketSession(seed=123)
    result = session.submit(
        side=Side.ASK,
        order_type=OrderType.LIMIT,
        quantity=1,
        price=1.00,
    )
    assert result["outcome"] == "needs_acknowledgement"
    assert result["collared_price"] > 1.00


def main() -> None:
    tests = [
        test_matching_engine_lifecycle,
        test_market_session_keeps_user_history,
        test_low_sell_limit_returns_acknowledgement,
    ]

    for test in tests:
        test()
        print(f"PASS: {test.__name__}")

    print("\nAll order-history tests passed.")


if __name__ == "__main__":
    main()
