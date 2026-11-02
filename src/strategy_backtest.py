"""Read-only A–S fair-value comparison for the supplied KIS futures CSVs."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Literal

from backtest_rules import evaluate_quote_fill
from matching import Side, TickScale
from strategies.avellaneda_stoikov import ASParameters, calculate_quotes
from strategies.as_market_maker import make_executable_quote

FairValueSource = Literal["mid", "micro", "theoretical"]


@dataclass(frozen=True)
class MarketDataRow:
    received_at: str
    last_price: float
    best_bid: float
    best_ask: float
    bid_quantity: int
    ask_quantity: int
    theoretical_price: float

    @classmethod
    def from_kis_row(cls, row: dict[str, str]) -> "MarketDataRow":
        return cls(
            received_at=row["received_at"],
            last_price=float(row["futs_prpr"]),
            best_bid=float(row["futs_bidp1"]),
            best_ask=float(row["futs_askp1"]),
            bid_quantity=int(float(row["bidp_rsqn1"])),
            ask_quantity=int(float(row["askp_rsqn1"])),
            theoretical_price=float(row["hts_thpr"]),
        )

    def fair_value(self, source: FairValueSource) -> float:
        if source == "theoretical":
            return self.theoretical_price
        if source == "micro":
            depth = self.bid_quantity + self.ask_quantity
            if depth > 0:
                return (
                    self.best_ask * self.bid_quantity
                    + self.best_bid * self.ask_quantity
                ) / depth
        return (self.best_bid + self.best_ask) / 2


@dataclass(frozen=True)
class BacktestResult:
    fair_value_source: str
    rows: int
    fills: int
    traded_quantity: int
    ending_inventory: int
    max_abs_inventory: int
    fees_paid: float
    ending_equity: float
    pnl: float

    def to_dict(self) -> dict:
        return asdict(self)


def read_kis_csv(path: str | Path) -> Iterator[MarketDataRow]:
    """Stream rows without writing to or modifying the source CSV."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as source:
        for raw_row in csv.DictReader(source):
            try:
                yield MarketDataRow.from_kis_row(raw_row)
            except (KeyError, TypeError, ValueError):
                continue


def run_backtest(
    rows: Iterable[MarketDataRow],
    fair_value_source: FairValueSource,
    *,
    risk_aversion: float = 0.1,
    kappa: float = 50.0,
    volatility: float = 0.05,
    quote_quantity: int = 10,
    inventory_limit: int = 100,
    fee_rate: float = 0.00003,
    tick_size: float = 0.05,
    initial_cash: float = 1_000_000_000.0,
    contract_multiplier: int = 250_000,
) -> BacktestResult:
    """Evaluate one fair-value variant with the PM's passive fill rules."""
    data = iter(rows)
    first = next(data, None)
    if first is None:
        raise ValueError("backtest requires at least one valid market-data row")

    parameters = ASParameters(risk_aversion=risk_aversion, kappa=kappa)
    scale = TickScale(tick_size)
    cash = initial_cash
    inventory = 0
    max_abs_inventory = 0
    fees_paid = 0.0
    fill_count = 0
    traded_quantity = 0
    row_count = 1

    def quotes(row: MarketDataRow):
        raw = calculate_quotes(
            mid_price=row.fair_value(fair_value_source),
            inventory=inventory,
            volatility=volatility,
            remaining_time=1.0,
            parameters=parameters,
        )
        return make_executable_quote(raw, scale)

    previous = first
    current_quotes = quotes(first)
    last = first

    for current in data:
        row_count += 1
        last = current
        candidates = (
            (Side.BID, current_quotes.bid_price),
            (Side.ASK, current_quotes.ask_price),
        )
        for side, quote_price in candidates:
            headroom = (
                inventory_limit - inventory
                if side is Side.BID
                else inventory_limit + inventory
            )
            quantity = min(quote_quantity, max(0, headroom))
            if quantity == 0:
                continue
            fill = evaluate_quote_fill(
                side=side,
                quote_price=quote_price,
                best_bid=previous.best_bid,
                best_ask=previous.best_ask,
                later_market_price=current.last_price,
            )
            if not fill.filled or fill.price is None:
                continue
            signed_quantity = side.sign * quantity
            traded_notional = fill.price * quantity * contract_multiplier
            fee = traded_notional * fee_rate
            cash -= signed_quantity * fill.price * contract_multiplier + fee
            inventory += signed_quantity
            fees_paid += fee
            fill_count += 1
            traded_quantity += quantity
            max_abs_inventory = max(max_abs_inventory, abs(inventory))

        previous = current
        current_quotes = quotes(current)

    ending_equity = cash + inventory * last.last_price * contract_multiplier
    return BacktestResult(
        fair_value_source=fair_value_source,
        rows=row_count,
        fills=fill_count,
        traded_quantity=traded_quantity,
        ending_inventory=inventory,
        max_abs_inventory=max_abs_inventory,
        fees_paid=fees_paid,
        ending_equity=ending_equity,
        pnl=ending_equity - initial_cash,
    )


def compare_fair_values(path: str | Path, **kwargs) -> list[dict]:
    """Run all three variants independently against the same unchanged file."""
    return [
        run_backtest(read_kis_csv(path), source, **kwargs).to_dict()
        for source in ("mid", "micro", "theoretical")
    ]
