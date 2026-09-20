import math
import sys
from pathlib import Path


# Allow imports from src/
SRC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_DIR))


from market_session import MarketSession
from matching import OrderType, Side


def make_session() -> MarketSession:
    session = MarketSession(seed=42)

    # Refresh on every tick so the tests do not need to wait.
    session.strategy_refresh_interval = 1

    return session


def test_market_maker_uses_session_engine() -> None:
    session = make_session()

    assert session.market_maker.engine is session.engine


def test_strategy_starts_disabled() -> None:
    session = make_session()

    assert session.strategy_enabled is False
    assert session.market_maker.active_bid_id is None
    assert session.market_maker.active_ask_id is None


def test_start_and_stop_strategy() -> None:
    session = make_session()

    session.start_strategy()
    assert session.strategy_enabled is True

    session.stop_strategy()
    assert session.strategy_enabled is False


def test_advancing_refreshes_strategy() -> None:
    session = make_session()

    session.configure(live=True)
    session.start_strategy()

    # Try multiple ticks in case the first tick does not yet have a midpoint.
    for _ in range(20):
        session.advance(1)

        if session.market_maker.last_quote is not None:
            break

    quote = session.market_maker.last_quote

    assert quote is not None
    assert quote.bid_ticks < quote.ask_ticks
    assert quote.bid_price < quote.ask_price


def test_refresh_is_not_skipped_at_tempo_five() -> None:
    session = make_session()
    session.strategy_refresh_interval = 5
    session.configure(live=True)
    session.start_strategy()

    # Sessions begin at tick 1. Modulo-based refresh logic would never run
    # when advancing in steps of five (6, 11, 16, ...).
    session.advance(5)

    assert session.market_maker.last_quote is not None


def test_active_ids_refer_to_active_orders() -> None:
    session = make_session()

    session.configure(live=True)
    session.start_strategy()

    for _ in range(20):
        session.advance(1)

        if session.market_maker.last_quote is not None:
            break

    bid_id = session.market_maker.active_bid_id
    ask_id = session.market_maker.active_ask_id

    # An ID can be None if the order was immediately filled.
    if bid_id is not None:
        bid_order = session.engine.find(bid_id)

        assert bid_order is not None
        assert bid_order.side is Side.BID

    if ask_id is not None:
        ask_order = session.engine.find(ask_id)

        assert ask_order is not None
        assert ask_order.side is Side.ASK


def test_stop_cancels_active_quotes() -> None:
    session = make_session()

    session.configure(live=True)
    session.start_strategy()

    for _ in range(20):
        session.advance(1)

        if (
            session.market_maker.active_bid_id is not None
            or session.market_maker.active_ask_id is not None
        ):
            break

    old_bid_id = session.market_maker.active_bid_id
    old_ask_id = session.market_maker.active_ask_id

    session.stop_strategy()

    assert session.strategy_enabled is False
    assert session.market_maker.active_bid_id is None
    assert session.market_maker.active_ask_id is None

    if old_bid_id is not None:
        assert session.engine.find(old_bid_id) is None

    if old_ask_id is not None:
        assert session.engine.find(old_ask_id) is None


def test_snapshot_contains_strategy_state() -> None:
    session = make_session()

    session.configure(live=True)
    session.start_strategy()

    for _ in range(20):
        session.advance(1)

        if session.market_maker.last_quote is not None:
            break

    snapshot = session.snapshot()

    assert "strategy" in snapshot

    strategy = snapshot["strategy"]

    assert strategy["enabled"] is True
    assert strategy["risk_aversion"] > 0
    assert strategy["kappa"] > 0
    assert strategy["order_quantity"] > 0

    quote = session.market_maker.last_quote

    assert quote is not None
    assert strategy["bid_price"] == quote.bid_price
    assert strategy["ask_price"] == quote.ask_price


def test_process_fills_updates_portfolio() -> None:
    session = make_session()

    # Remove the generated book so this test has a controlled trade.
    session.engine.reset()

    initial_cash = session.cash
    initial_inventory = session.inventory

    # A non-user order rests on the ask side.
    resting_report = session.engine.place_limit(
        side=Side.ASK,
        price=100.0,
        quantity=2,
        actor="flow",
    )

    assert resting_report.open_qty == 2

    # The user buys those two units.
    user_report = session.engine.place_market(
        side=Side.BID,
        quantity=2,
        actor="user",
    )

    assert len(user_report.fills) == 1

    session._process_fills(user_report.fills)

    print("initial inventory:", initial_inventory)
    print("final inventory:", session.inventory)
    print("fills:", user_report.fills)

    assert session.inventory == initial_inventory + 2
    assert math.isclose(
        session.cash,
        initial_cash - 200.0,
        rel_tol=1e-9,
        abs_tol=1e-9,
    )


def test_restart_resets_strategy() -> None:
    session = make_session()

    session.configure(live=True)
    session.start_strategy()

    for _ in range(20):
        session.advance(1)

        if session.market_maker.last_quote is not None:
            break

    session.restart()

    assert session.strategy_enabled is False
    assert session.market_maker.active_bid_id is None
    assert session.market_maker.active_ask_id is None
    assert session.market_maker.last_quote is None


def run_test(test_function) -> None:
    try:
        test_function()
        print(f"PASS: {test_function.__name__}")
    except Exception:
        print(f"FAIL: {test_function.__name__}")
        raise


if __name__ == "__main__":
    tests = [
        test_market_maker_uses_session_engine,
        test_strategy_starts_disabled,
        test_start_and_stop_strategy,
        test_advancing_refreshes_strategy,
        test_refresh_is_not_skipped_at_tempo_five,
        test_active_ids_refer_to_active_orders,
        test_stop_cancels_active_quotes,
        test_snapshot_contains_strategy_state,
        test_process_fills_updates_portfolio,
        test_restart_resets_strategy,
    ]

    for test in tests:
        run_test(test)
