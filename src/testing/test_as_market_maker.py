import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_DIR))

from strategies.avellaneda_stoikov import ASParameters, ASQuote
from strategies.as_market_maker import (
    ASMarketMaker,
    ExecutableQuote,
    make_executable_quote,
)
from matching import MatchingEngine, TickScale


def make_market_maker() -> ASMarketMaker:
    engine = MatchingEngine(TickScale(size=0.01))

    parameters = ASParameters(
        risk_aversion=0.1,
        kappa=1.5,
        target_inventory=0,
    )

    return ASMarketMaker(
        engine=engine,
        parameters=parameters,
        total_ticks=100,
        order_quantity=10,
    )


def test_make_executable_quote() -> None:
    scale = TickScale(size=0.01)

    raw_quote = ASQuote(
        reservation_price=100.0,
        spread=0.022,
        bid_price=99.989,
        ask_price=100.011,
    )

    quote = make_executable_quote(raw_quote, scale)

    # Bid rounds downward and ask rounds upward.
    assert quote.bid_ticks == 9998
    assert quote.ask_ticks == 10002
    assert quote.bid_price == 99.98
    assert quote.ask_price == 100.02

    assert quote.bid_ticks < quote.ask_ticks
    assert quote.bid_price < quote.ask_price


def test_constructor_keeps_dependencies() -> None:
    engine = MatchingEngine()
    parameters = ASParameters(
        risk_aversion=0.1,
        kappa=1.5,
    )

    market_maker = ASMarketMaker(
        engine=engine,
        parameters=parameters,
        total_ticks=200,
        order_quantity=15,
    )

    assert market_maker.engine is engine
    assert market_maker.parameters is parameters
    assert market_maker.total_ticks == 200
    assert market_maker.order_quantity == 15
    assert market_maker.active_bid_id is None
    assert market_maker.active_ask_id is None


def test_constructor_rejects_invalid_values() -> None:
    engine = MatchingEngine()
    parameters = ASParameters(
        risk_aversion=0.1,
        kappa=1.5,
    )

    try:
        ASMarketMaker(
            engine=engine,
            parameters=parameters,
            total_ticks=0,
            order_quantity=10,
        )
        raise AssertionError("Expected total_ticks=0 to raise ValueError")
    except ValueError:
        pass

    try:
        ASMarketMaker(
            engine=engine,
            parameters=parameters,
            total_ticks=100,
            order_quantity=0,
        )
        raise AssertionError("Expected order_quantity=0 to raise ValueError")
    except ValueError:
        pass


def test_remaining_time() -> None:
    market_maker = make_market_maker()

    assert market_maker.remaining_time(0) == 1.0
    assert market_maker.remaining_time(25) == 0.75
    assert market_maker.remaining_time(50) == 0.5
    assert market_maker.remaining_time(100) == 0.0

    # Values outside the session should be clamped.
    assert market_maker.remaining_time(-10) == 1.0
    assert market_maker.remaining_time(150) == 0.0


def test_calculate_executable_quote() -> None:
    market_maker = make_market_maker()

    quote = market_maker.calculate_executable_quote(
        mid_price=100.0,
        inventory=0,
        volatility=1.0,
        current_tick=0,
    )

    assert isinstance(quote, ExecutableQuote)
    assert quote.bid_ticks < quote.ask_ticks
    assert quote.bid_price < quote.ask_price

    # With zero inventory and a zero target, the quotes should surround
    # the mid-price.
    assert quote.bid_price < 100.0
    assert quote.ask_price > 100.0


def test_refresh_places_bid_and_ask() -> None:
    market_maker = make_market_maker()

    expected_quote = market_maker.calculate_executable_quote(
        mid_price=100.0,
        inventory=0,
        volatility=1.0,
        current_tick=0,
    )

    bid_report, ask_report = market_maker.refresh(
        mid_price=100.0,
        inventory=0,
        volatility=1.0,
        current_tick=0,
    )

    assert bid_report.order_id != ask_report.order_id

    assert market_maker.active_bid_id == bid_report.order_id
    assert market_maker.active_ask_id == ask_report.order_id

    bid_order = market_maker.engine.find(bid_report.order_id)
    ask_order = market_maker.engine.find(ask_report.order_id)

    assert bid_order is not None
    assert ask_order is not None

    assert bid_order.limit_ticks == expected_quote.bid_ticks
    assert ask_order.limit_ticks == expected_quote.ask_ticks

    assert bid_order.open_qty == market_maker.order_quantity
    assert ask_order.open_qty == market_maker.order_quantity


def test_refresh_replaces_previous_quotes() -> None:
    market_maker = make_market_maker()

    market_maker.refresh(
        mid_price=100.0,
        inventory=0,
        volatility=1.0,
        current_tick=0,
    )

    old_bid_id = market_maker.active_bid_id
    old_ask_id = market_maker.active_ask_id

    assert old_bid_id is not None
    assert old_ask_id is not None

    market_maker.refresh(
        mid_price=101.0,
        inventory=5,
        volatility=1.0,
        current_tick=10,
    )

    # Previous quotes should no longer be active.
    assert market_maker.engine.find(old_bid_id) is None
    assert market_maker.engine.find(old_ask_id) is None

    # New quotes should have different IDs and should be active.
    assert market_maker.active_bid_id is not None
    assert market_maker.active_ask_id is not None

    assert market_maker.active_bid_id != old_bid_id
    assert market_maker.active_ask_id != old_ask_id

    assert market_maker.engine.find(
        market_maker.active_bid_id
    ) is not None

    assert market_maker.engine.find(
        market_maker.active_ask_id
    ) is not None


def test_cancel_active_quotes() -> None:
    market_maker = make_market_maker()

    market_maker.refresh(
        mid_price=100.0,
        inventory=0,
        volatility=1.0,
        current_tick=0,
    )

    bid_id = market_maker.active_bid_id
    ask_id = market_maker.active_ask_id

    market_maker.cancel_active_quotes()

    assert market_maker.active_bid_id is None
    assert market_maker.active_ask_id is None

    assert market_maker.engine.find(bid_id) is None
    assert market_maker.engine.find(ask_id) is None


def run_test(test_function) -> None:
    try:
        test_function()
        print(f"PASS: {test_function.__name__}")
    except Exception:
        print(f"FAIL: {test_function.__name__}")
        raise


if __name__ == "__main__":
    tests = [
        test_make_executable_quote,
        test_constructor_keeps_dependencies,
        test_constructor_rejects_invalid_values,
        test_remaining_time,
        test_calculate_executable_quote,
        test_refresh_places_bid_and_ask,
        test_refresh_replaces_previous_quotes,
        test_cancel_active_quotes,
    ]

    for test in tests:
        run_test(test)