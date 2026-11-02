"""Replay collected KIS futures feeds through the matching engine, read-only."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from matching import Fill, MatchingEngine, Side


@dataclass
class ReplaySettings:
    seed: int | None = None
    urgency: float = 0.0


@dataclass
class ReplayFairValue:
    value: float = 0.0


@dataclass(frozen=True)
class TradeReference:
    received_at: str
    last_price: float
    theoretical_price: float
    quantity: int


class MarketDataReplay:
    """Streams 011 order-book rows and time-aligns the latest 010 trade row."""

    def __init__(
        self,
        engine: MatchingEngine,
        orderbook_path: str | Path,
        trades_path: str | Path | None = None,
    ) -> None:
        self.engine = engine
        self.orderbook_path = Path(orderbook_path)
        self.trades_path = Path(trades_path) if trades_path is not None else None
        self.settings = ReplaySettings()
        self.fair_value = ReplayFairValue()
        self.ticks_elapsed = 0
        self.current_timestamp: str | None = None
        self.last_price: float | None = None
        self.finished = False
        self._external_order_ids: set[int] = set()
        self._orderbook_file = None
        self._trade_file = None
        self._orderbook_rows: Iterator[dict[str, str]] | None = None
        self._trade_rows: Iterator[dict[str, str]] | None = None
        self._next_trade: TradeReference | None = None
        self._latest_trade: TradeReference | None = None
        self._previous_trade_price: float | None = None
        self._queue_ahead: dict[int, int] = {}
        self._visible_levels: dict[tuple[Side, int], int] = {}
        self.market_best_bid: float | None = None
        self.market_best_ask: float | None = None
        self._open_streams()

    def _open_streams(self) -> None:
        self.close()
        self._orderbook_file = self.orderbook_path.open(
            "r", encoding="utf-8-sig", newline=""
        )
        self._orderbook_rows = iter(csv.DictReader(self._orderbook_file))
        if self.trades_path is not None and self.trades_path.exists():
            self._trade_file = self.trades_path.open(
                "r", encoding="utf-8-sig", newline=""
            )
            self._trade_rows = iter(csv.DictReader(self._trade_file))
            self._next_trade = self._read_trade()

    def close(self) -> None:
        if self._orderbook_file is not None:
            self._orderbook_file.close()
        if self._trade_file is not None:
            self._trade_file.close()
        self._orderbook_file = None
        self._trade_file = None

    def _read_trade(self) -> TradeReference | None:
        if self._trade_rows is None:
            return None
        for row in self._trade_rows:
            try:
                return TradeReference(
                    received_at=row["received_at"],
                    last_price=float(row["futs_prpr"]),
                    theoretical_price=float(row["hts_thpr"]),
                    quantity=max(0, int(float(row["last_cnqn"]))),
                )
            except (KeyError, TypeError, ValueError):
                continue
        return None

    def _infer_taker_side(self, trade_price: float) -> Side:
        if self.market_best_ask is not None and trade_price >= self.market_best_ask:
            return Side.BID
        if self.market_best_bid is not None and trade_price <= self.market_best_bid:
            return Side.ASK
        if self._previous_trade_price is not None:
            if trade_price > self._previous_trade_price:
                return Side.BID
            if trade_price < self._previous_trade_price:
                return Side.ASK
        midpoint = None
        if self.market_best_bid is not None and self.market_best_ask is not None:
            midpoint = (self.market_best_bid + self.market_best_ask) / 2
        return Side.BID if midpoint is None or trade_price >= midpoint else Side.ASK

    def _process_trade(self, trade: TradeReference) -> list[Fill]:
        taker_side = self._infer_taker_side(trade.last_price)
        resting_side = taker_side.contra
        candidates = [
            order
            for order in self.engine.resting_orders(resting_side)
            if order.actor == "user" and order.limit_ticks is not None
        ]
        candidates.sort(
            key=lambda order: (
                -order.limit_ticks if resting_side is Side.BID else order.limit_ticks,
                order.arrival,
            )
        )
        remaining_trade_quantity = trade.quantity
        fills: list[Fill] = []
        for order in candidates:
            order_price = self.engine.scale.to_price(order.limit_ticks)
            reached = (
                trade.last_price <= order_price
                if resting_side is Side.BID
                else trade.last_price >= order_price
            )
            if not reached or remaining_trade_quantity <= 0:
                continue
            queue_ahead = self._queue_ahead.get(order.order_id, 0)
            consumed_ahead = min(queue_ahead, remaining_trade_quantity)
            queue_ahead -= consumed_ahead
            remaining_trade_quantity -= consumed_ahead
            self._queue_ahead[order.order_id] = queue_ahead
            if remaining_trade_quantity <= 0:
                continue
            fill = self.engine.execute_resting_order(
                order.order_id,
                remaining_trade_quantity,
                order_price,
                taker_side,
            )
            if fill is not None:
                fills.append(fill)
                remaining_trade_quantity -= fill.quantity
                if self.engine.find(order.order_id) is None:
                    self._queue_ahead.pop(order.order_id, None)
        self._previous_trade_price = trade.last_price
        return fills

    def _sync_trade_reference(self, timestamp: str) -> list[Fill]:
        fills: list[Fill] = []
        while self._next_trade is not None and self._next_trade.received_at <= timestamp:
            self._latest_trade = self._next_trade
            fills.extend(self._process_trade(self._next_trade))
            self._next_trade = self._read_trade()
        return fills

    @staticmethod
    def _levels(row: dict[str, str], side: Side) -> list[tuple[float, int]]:
        price_prefix = "futs_bidp" if side is Side.BID else "futs_askp"
        quantity_prefix = "bidp_rsqn" if side is Side.BID else "askp_rsqn"
        levels: list[tuple[float, int]] = []
        for level in range(1, 6):
            try:
                price = float(row[f"{price_prefix}{level}"])
                quantity = int(float(row[f"{quantity_prefix}{level}"]))
            except (KeyError, TypeError, ValueError):
                continue
            if price > 0 and quantity > 0:
                levels.append((price, quantity))
        return levels

    def _remove_previous_snapshot(self) -> None:
        for order_id in self._external_order_ids:
            self.engine.pull(order_id)
        self._external_order_ids.clear()

    def register_shadow_order(self, order_id: int) -> None:
        """Place a newly resting user order behind recorded same-price quantity."""
        order = self.engine.find(order_id)
        if order is None or order.limit_ticks is None:
            return
        key = (order.side, order.limit_ticks)
        self._queue_ahead[order_id] = self._visible_levels.get(key, 0)

    def market_microprice(self) -> float | None:
        if self.market_best_bid is None or self.market_best_ask is None:
            return None
        bid_ticks = self.engine.scale.to_ticks(self.market_best_bid)
        ask_ticks = self.engine.scale.to_ticks(self.market_best_ask)
        bid_quantity = self._visible_levels.get((Side.BID, bid_ticks), 0)
        ask_quantity = self._visible_levels.get((Side.ASK, ask_ticks), 0)
        total = bid_quantity + ask_quantity
        if total <= 0:
            return None
        return (
            self.market_best_ask * bid_quantity
            + self.market_best_bid * ask_quantity
        ) / total

    def _update_shadow_queues(self) -> None:
        for order_id in list(self._queue_ahead):
            order = self.engine.find(order_id)
            if order is None or order.limit_ticks is None:
                self._queue_ahead.pop(order_id, None)
                continue
            visible = self._visible_levels.get((order.side, order.limit_ticks), 0)
            self._queue_ahead[order_id] = min(self._queue_ahead[order_id], visible)

    def _apply_orderbook_row(self, row: dict[str, str]) -> list[Fill]:
        timestamp = row.get("received_at")
        if not timestamp:
            return []
        fills = self._sync_trade_reference(timestamp)
        bids = self._levels(row, Side.BID)
        asks = self._levels(row, Side.ASK)
        if not bids or not asks:
            return []

        self._remove_previous_snapshot()
        self._visible_levels.clear()

        # Aggressive levels arrive first so crossings follow exchange price priority.
        for side, levels in ((Side.BID, bids), (Side.ASK, asks)):
            for price, quantity in levels:
                report = self.engine.place_snapshot_limit(side, price, quantity, actor="replay")
                if self.engine.find(report.order_id) is not None:
                    self._external_order_ids.add(report.order_id)
                ticks = self.engine.scale.to_ticks(price)
                self._visible_levels[(side, ticks)] = quantity

        self._update_shadow_queues()

        self.current_timestamp = timestamp
        self.market_best_bid = bids[0][0]
        self.market_best_ask = asks[0][0]
        midpoint = (bids[0][0] + asks[0][0]) / 2
        if self._latest_trade is not None:
            self.last_price = self._latest_trade.last_price
            self.fair_value.value = self._latest_trade.theoretical_price
        else:
            self.last_price = midpoint
            self.fair_value.value = midpoint
        self.ticks_elapsed += 1
        return fills

    def advance(self, ticks: int = 1) -> list[Fill]:
        fills: list[Fill] = []
        if self.finished or self._orderbook_rows is None:
            return fills
        for _ in range(ticks):
            try:
                row = next(self._orderbook_rows)
            except StopIteration:
                self.finished = True
                self.close()
                break
            fills.extend(self._apply_orderbook_row(row))
        return fills
