from dataclasses import dataclass
from matching import TickScale, MatchingEngine, Side
from .avellaneda_stoikov import ASParameters, ASQuote, calculate_quotes

@dataclass(frozen=True)
class ExecutableQuote:
    bid_ticks: int
    ask_ticks: int
    bid_price: float
    ask_price: float


def make_executable_quote(quote: ASQuote, scale: TickScale) -> ExecutableQuote:
    # raw bid/ask price -> price
    bid_ticks = scale.floor_to_ticks(quote.bid_price)
    ask_ticks = scale.ceil_to_ticks(quote.ask_price)

    if bid_ticks >= ask_ticks:
        raise ValueError("bid 가 ask 보다 적은 값이어야 합니다.")
    
    # snap them to acceptable price
    bid_price = scale.to_price(bid_ticks)
    ask_price = scale.to_price(ask_ticks)
    
    return ExecutableQuote(
        bid_ticks = bid_ticks,
        ask_ticks = ask_ticks,
        bid_price = bid_price,
        ask_price = ask_price,
    )


class ASMarketMaker:
    def __init__(
            self,
            engine: MatchingEngine,
            parameters: ASParameters,
            total_ticks: int,
            order_quantity: int,
    ) -> None:
        if total_ticks <= 0:
            raise ValueError("total ticks 는 0보다 커야 합니다.")
        
        if order_quantity <= 0:
            raise ValueError("order quantity 는 0보다 커야 합니다.")
        
        self.engine = engine
        self.parameters = parameters
        self.total_ticks = total_ticks
        self.order_quantity = order_quantity
        self.active_bid_id: int | None = None
        self.active_ask_id: int | None = None
        self.last_quote: ExecutableQuote | None = None

    def remaining_time(self, current_tick: int) -> float:
        remaining = (self.total_ticks - current_tick) / self.total_ticks
        return max(0.0, min(1.0, remaining))
    
    def cancel_active_quotes(self) -> None:
        if self.active_bid_id is not None:
            self.engine.pull(self.active_bid_id)
            self.active_bid_id = None

        if self.active_ask_id is not None:
            self.engine.pull(self.active_ask_id)
            self.active_ask_id = None

    def calculate_executable_quote(
            self,
            mid_price: float,
            inventory: int,
            volatility: float,
            current_tick: int,
    ) -> ExecutableQuote:
        # calculate the remaining time
        remaining_time = self.remaining_time(current_tick)

        raw_quote = calculate_quotes(
            mid_price=mid_price,
            inventory=inventory,
            volatility=volatility, 
            remaining_time=remaining_time,
            parameters=self.parameters,
        )
        
        executable_quote = make_executable_quote(
            quote = raw_quote, 
            scale = self.engine.scale,
        )

        return executable_quote
    
    def refresh(self, mid_price: float, inventory: int, volatility: float, current_tick: int,):
        # calculate the new executable quote 
        quote = self.calculate_executable_quote(mid_price, inventory, volatility, current_tick)
        self.last_quote = quote
        # cancel the previous bid and ask
        self.cancel_active_quotes()

        # submit the new bid/ask limit order
        bid_report = self.engine.place_limit(
            side=Side.BID,
            price=quote.bid_price,
            quantity=self.order_quantity, 
            actor="user",
        )

        ask_report = self.engine.place_limit(
            side=Side.ASK,
            price=quote.ask_price,
            quantity=self.order_quantity, 
            actor="user",
        )

        if self.engine.find(bid_report.order_id) is not None:
            self.active_bid_id = bid_report.order_id
        else: 
            self.active_bid_id = None

        if self.engine.find(ask_report.order_id) is not None:
            self.active_ask_id = ask_report.order_id
        else: 
            self.active_ask_id = None

        return bid_report, ask_report
            
