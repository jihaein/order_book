from matching import MatchingEngine, TickScale, Fill, Side, OrderType, OrderStatus
from flow import FlowGenerator, FlowSettings
from collections import deque
from time import strftime
from dataclasses import dataclass, field

@dataclass(frozen=True)
class BandVerdict:
    within: bool
    price: float
    reason: str = ""

class MarketSession:
    def __init__(self, scale: TickScale | None = None, seed: int | None = None) -> None:
        self.engine = MatchingEngine(scale)
        self.flow = FlowGenerator(self.engine, FlowSettings(seed=seed))
        self.live: bool = False
        self.tempo: int = 4
        PRINT_HISTORY = 100
        self.prints = deque(maxlen=PRINT_HISTORY)
        self.my_orders: set[int] = set()
        self.last_print: float | None = None
        self.flow.advance()


    def _record(self, fills: list[Fill]) -> None:
        record = {}
        for fill in fills:
            print_data = {
                "at": strftime("%H:%M:%S"),
                "price": fill.price,
                "quantity": fill.quantity,
                "taker": fill.taker_side.value,
            }

            self.prints.appendleft(print_data)
            self.last_print = fill.price

    def advance(self, ticks: int=1) -> None:
        if not self.live:
            return
        else: 
            self._record(self.flow.advance(ticks))
    
    def restart(self) -> None:
        self.engine.reset()
        self.flow = FlowGenerator(
            self.engine,
            FlowSettings(seed=self.flow.settings.seed)
        )
        self.prints.clear()
        self.my_orders.clear()
        self.last_print = None
        fills = self.flow.advance()
        self._record(fills)
    
    def configure(self, live=None, tempo=None, urgency=None) -> None:
        if live is not None:
            self.live = live 

        if tempo is not None:
            self.tempo = max(1, min(tempo, 20))

        if urgency is not None: 
            self.flow.settings.urgency = max(0, min(urgency, 5))

    def anchor_price(self) -> float:
        mid = self.engine.mid()
        if mid is not None: return mid
        if self.last_print is not None: return self.last_print
        return self.flow.fair_value.value
    
    def vet_limit(self, side: Side, price: float) -> BandVerdict:
        ref = self.anchor_price()
        ceiling = ref * 1.10
        floor = ref * 0.90

        if side is Side.BID and price > ceiling:
            pct_above = (price / ref-1) * 100
            pct_below = (1 - price / ref) * 100

            return BandVerdict(
                within=False,
                price=ceiling,
                reason=(f"BID at {price:,.2f} 는 시장가보다 {pct_above:,.0f}% 더 높습니다. 주문은 ceiling 값인 {ceiling:,.2f} 으로 고정됩니다."),
            )
        
        if side is Side.ASK and price < floor:
            return BandVerdict(
                within=False,
                price=floor,
                reason=(f"ASK at {price:,.2f} 는 시장가보다 {pct_below:,.0f}% 더 낮습니다. 주문은 floor 값인 {floor:,.2f} 으로 고정됩니다."),
            )
        
        return BandVerdict(
            within = True,
            price = price,
        )
    
    def submit(self, side:Side, order_type: OrderType, quantity: int, price: float | None = None, acknowledged: bool=False) -> dict:
        outcome = {}
        if quantity <= 0:
            return{
                "outcome": "rejected",
                "reason": "수량이 0보다 커야합니다."
            }
        
        if order_type is OrderType.MARKET:
            report = self.engine.place_market(
                side,
                quantity,
                actor="user",
            )
        
        elif order_type is OrderType.LIMIT:
            if price is None:
                return {
                    "outcome" : "rejected",
                    "reason" : "지정자 주문에 가격이 빠졌습니다."
                }
            
            verdict = self.vet_limit(side, price)

            if not verdict.within and not acknowledged:
                return{
                    "outcome": "needs_acknowledgement",
                    "reason": verdict.reason,
                    "collared_price": verdict.price,
                }
            
            report = self.engine.place_limit(side, verdict.price, quantity, actor="user")

        else:
            return{
                "outcome": "rejected",
                "reason": "지정가주문 또는 시장가주문 둘 중에 하나를 선택하세요."
            }
        
        self._record(report.fills)

        if order_type is OrderType.LIMIT and report.open_qty > 0:
            self.my_orders.add(report.order_id)

        return {
            "outcome": "accepted",
            "order_id": report.order_id,
            "status": report.status.value,
            "filled": report.filled_qty,
            "open": report.open_qty,
            "average_price": report.average_price,
            "fills": [{ "price": fill.price, "quantity": fill.quantity, "taker": fill.taker_side.value,}
                for fill in report.fills]
        }
        
    
    def pull_mine(self, order_id: int) -> bool:
        if order_id not in self.my_orders:
            return False
        
        removed = self.engine.pull(order_id)
        if removed is None:
            return False
        
        self.my_orders.discard(order_id)
        return True
    
    
    def snapshot(self, depth: int = 10) -> dict:
        self.my_orders = {
            order_id
            for order_id in self.my_orders
            if order_id in self.engine
        }

        best_bid = self.engine.best_bid()
        best_ask = self.engine.best_ask()
        mid = self.engine.mid()
        spread = self.engine.spread()

        bids = self.engine.ladder(Side.BID, depth)
        asks = self.engine.ladder(Side.ASK, depth)

        return {
            "live": self.live,
            "tempo": self.tempo,
            "urgency": self.flow.settings.urgency,

            "clock": {
                "ticks": self.flow.ticks_elapsed,
            },

            "top": {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid": mid,
                "spread": spread,
                "fair_value": self.flow.fair_value.value,
                "last_print": self.last_print,
            },
            
            "book": {
            "bids": [
                {"price": price,
                 "quantity": quantity,}
                for price, quantity in bids
            ],
            "asks": [
                {"price": price,
                 "quantity": quantity,}
                for price, quantity in asks
            ],
        },

        "prints": list(self.prints),

        "my_orders": [
            {"order_id": order.order_id,
             "side": order.side.value,
             "quantity": order.open_qty,
             "price": (self.engine.scale.to_price(order.limit_ticks)
                    if order.limit_ticks is not None else None),}
            for order_id in self.my_orders
            if (order := self.engine.find(order_id)) is not None
        ],
    }