"""Read-only fill rules for evaluating our quotes against market-data rows.

These functions never mutate input data. A future CSV adapter only needs to map
its bid/ask/theoretical-price columns into the arguments below.
"""

from dataclasses import dataclass
from enum import Enum

from matching import Side


class QueuePosition(Enum):
    IMPROVING = "improving"
    AT_BEST = "at_best"
    BEHIND = "behind"
    MARKETABLE = "marketable"


@dataclass(frozen=True)
class BacktestFill:
    filled: bool
    price: float | None
    position: QueuePosition
    reason: str


def classify_quote(
    side: Side,
    quote_price: float,
    best_bid: float,
    best_ask: float,
) -> QueuePosition:
    """정균이가 준 룰 대로 implement 함."""
    if side is Side.BID:
        if quote_price >= best_ask:
            return QueuePosition.MARKETABLE
        if quote_price > best_bid:
            return QueuePosition.IMPROVING
        if quote_price == best_bid:
            return QueuePosition.AT_BEST
        return QueuePosition.BEHIND

    if quote_price <= best_bid:
        return QueuePosition.MARKETABLE
    if quote_price < best_ask:
        return QueuePosition.IMPROVING
    if quote_price == best_ask:
        return QueuePosition.AT_BEST
    return QueuePosition.BEHIND


def evaluate_quote_fill(
    side: Side,
    quote_price: float,
    best_bid: float,
    best_ask: float,
    later_market_price: float,
) -> BacktestFill:
    """Apply the supplied crossing rule without changing the source data.

    A marketable quote executes immediately at the resting contra best. Passive
    bids fill only after the observed market moves below the quote; passive asks
    fill only after it moves above the quote. Passive fills use our quote price,
    matching the PM's table.
    """
    position = classify_quote(side, quote_price, best_bid, best_ask)
    if position is QueuePosition.MARKETABLE:
        execution_price = best_ask if side is Side.BID else best_bid
        return BacktestFill(True, execution_price, position, "crossed contra best")

    crossed = (
        later_market_price < quote_price
        if side is Side.BID
        else later_market_price > quote_price
    )
    return BacktestFill(
        filled=crossed,
        price=quote_price if crossed else None,
        position=position,
        reason="market passed quote" if crossed else "waiting for market to pass quote",
    )
