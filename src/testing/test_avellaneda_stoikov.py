"""Tests for the pure Avellaneda-Stoikov quote calculator.

Place this file at ``src/testing/test_avellaneda_stoikov.py`` and run it from
the project root:

    python src/testing/test_avellaneda_stoikov.py

This script uses ordinary assertions, so pytest is not required.
"""

import sys
from math import isclose
from pathlib import Path
from typing import Callable


# This test lives in src/testing, while the strategies package lives in src.
SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from strategies.avellaneda_stoikov import (
    ASParameters,
    calculate_quotes,
)


REL_TOL = 1e-9
ABS_TOL = 1e-9


def assert_close(actual: float, expected: float, label: str) -> None:
    assert isclose(actual, expected, rel_tol=REL_TOL, abs_tol=ABS_TOL), (
        f"{label}: expected {expected}, got {actual}"
    )


def assert_raises_value_error(action: Callable[[], object], label: str) -> None:
    try:
        action()
    except ValueError:
        return
    raise AssertionError(f"{label}: expected ValueError")


def default_parameters() -> ASParameters:
    return ASParameters(
        risk_aversion=0.1,
        kappa=1.5,
        target_inventory=0,
    )


def test_numerical_example() -> None:
    quote = calculate_quotes(
        mid_price=100.0,
        inventory=5,
        volatility=1.0,
        remaining_time=1.0,
        parameters=default_parameters(),
    )

    assert_close(quote.reservation_price, 99.5, "reservation price")
    assert_close(quote.spread, 1.3907704227514235, "spread")
    assert_close(quote.bid_price, 98.80461478862429, "bid price")
    assert_close(quote.ask_price, 100.19538521137571, "ask price")


def test_zero_inventory_is_centered_on_mid() -> None:
    quote = calculate_quotes(
        mid_price=100.0,
        inventory=0,
        volatility=1.0,
        remaining_time=1.0,
        parameters=default_parameters(),
    )

    assert_close(quote.reservation_price, 100.0, "neutral reservation price")
    assert quote.bid_price < quote.reservation_price
    assert quote.reservation_price < quote.ask_price
    assert_close(
        quote.reservation_price - quote.bid_price,
        quote.ask_price - quote.reservation_price,
        "symmetric half-spreads",
    )


def test_long_inventory_shifts_quotes_down() -> None:
    quote = calculate_quotes(
        mid_price=100.0,
        inventory=10,
        volatility=1.0,
        remaining_time=1.0,
        parameters=default_parameters(),
    )

    assert quote.reservation_price < 100.0


def test_short_inventory_shifts_quotes_up() -> None:
    quote = calculate_quotes(
        mid_price=100.0,
        inventory=-10,
        volatility=1.0,
        remaining_time=1.0,
        parameters=default_parameters(),
    )

    assert quote.reservation_price > 100.0


def test_target_inventory_is_used() -> None:
    parameters = ASParameters(
        risk_aversion=0.1,
        kappa=1.5,
        target_inventory=5,
    )

    quote = calculate_quotes(
        mid_price=100.0,
        inventory=5,
        volatility=1.0,
        remaining_time=1.0,
        parameters=parameters,
    )

    assert_close(quote.reservation_price, 100.0, "target inventory reservation")


def test_spread_relationships() -> None:
    quote = calculate_quotes(
        mid_price=100.0,
        inventory=3,
        volatility=1.2,
        remaining_time=0.6,
        parameters=default_parameters(),
    )

    assert quote.bid_price < quote.reservation_price < quote.ask_price
    assert_close(quote.ask_price - quote.bid_price, quote.spread, "total spread")


def test_higher_volatility_widens_spread() -> None:
    low_volatility = calculate_quotes(
        mid_price=100.0,
        inventory=0,
        volatility=0.5,
        remaining_time=1.0,
        parameters=default_parameters(),
    )
    high_volatility = calculate_quotes(
        mid_price=100.0,
        inventory=0,
        volatility=2.0,
        remaining_time=1.0,
        parameters=default_parameters(),
    )

    assert high_volatility.spread > low_volatility.spread


def test_end_of_session_removes_inventory_skew() -> None:
    quote = calculate_quotes(
        mid_price=100.0,
        inventory=25,
        volatility=2.0,
        remaining_time=0.0,
        parameters=default_parameters(),
    )

    assert_close(quote.reservation_price, 100.0, "end-of-session reservation")


def test_invalid_inputs() -> None:
    parameters = default_parameters()

    assert_raises_value_error(
        lambda: calculate_quotes(0.0, 0, 1.0, 1.0, parameters),
        "nonpositive mid-price",
    )
    assert_raises_value_error(
        lambda: calculate_quotes(100.0, 0, -1.0, 1.0, parameters),
        "negative volatility",
    )
    assert_raises_value_error(
        lambda: calculate_quotes(
            100.0,
            0,
            1.0,
            1.0,
            ASParameters(risk_aversion=0.0, kappa=1.5),
        ),
        "nonpositive risk aversion",
    )
    assert_raises_value_error(
        lambda: calculate_quotes(
            100.0,
            0,
            1.0,
            1.0,
            ASParameters(risk_aversion=0.1, kappa=0.0),
        ),
        "nonpositive kappa",
    )
    assert_raises_value_error(
        lambda: calculate_quotes(100.0, 0, 1.0, -0.1, parameters),
        "remaining time below zero",
    )
    assert_raises_value_error(
        lambda: calculate_quotes(100.0, 0, 1.0, 1.1, parameters),
        "remaining time above one",
    )


def main() -> None:
    tests = [
        test_numerical_example,
        test_zero_inventory_is_centered_on_mid,
        test_long_inventory_shifts_quotes_down,
        test_short_inventory_shifts_quotes_up,
        test_target_inventory_is_used,
        test_spread_relationships,
        test_higher_volatility_widens_spread,
        test_end_of_session_removes_inventory_skew,
        test_invalid_inputs,
    ]

    for test in tests:
        test()
        print(f"PASS: {test.__name__}")

    print("\nAll Avellaneda-Stoikov quote tests passed.")


if __name__ == "__main__":
    main()
