from matching import MatchingEngine, TickScale, Fill, Side, OrderType, OrderStatus
from flow import FlowGenerator, FlowSettings
from collections import deque
from time import strftime
from dataclasses import dataclass, field
from strategies.avellaneda_stoikov import ASParameters
from strategies.as_market_maker import ASMarketMaker

@dataclass(frozen=True)
class BandVerdict:
    within: bool
    price: float
    reason: str = ""

class MarketSession:
    def __init__(self, scale: TickScale | None = None, seed: int | None = None, initial_cash: float = 1_000_000.0) -> None:
        self.engine = MatchingEngine(scale)
        self.flow = FlowGenerator(self.engine, FlowSettings(seed=seed))
        self.live: bool = False
        self.tempo: int = 4
        PRINT_HISTORY = 100
        self.prints = deque(maxlen=PRINT_HISTORY)
        self.my_orders: set[int] = set() # stores order_id
        self.last_print: float | None = None
        self.flow.advance()

        # this is for inventory tracking
        if initial_cash < 0:
            raise ValueError("돈이 0보다 많아야 합니다.")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.inventory = 0

        # AS Model
        self.strategy_enabled = False
        self.strategy_volatility = 0.05
        self.strategy_refresh_interval = 10
        self.strategy_order_ids: set[int] = set()
        self._last_strategy_refresh_tick: int | None = None
        self.market_maker = ASMarketMaker(
            engine=self.engine,
            parameters=ASParameters(
                risk_aversion=0.1,
                kappa=50,
                target_inventory=0,
            ),
            total_ticks=10_000,
            order_quantity=10,
        )

    # ===== AS Model ===
    def start_strategy(self) -> None:
        self.strategy_enabled = True
        self._last_strategy_refresh_tick = None

    def stop_strategy(self) -> None:
        self.strategy_enabled = False
        self.market_maker.cancel_active_quotes()

    # AS Model
    def _process_fills(self, fills: list[Fill]) -> None:
        if not fills:
            return
        self._record(fills)
        for fill in fills:
            self._account_for_fill(fill)

    def _refresh_strategy(self) -> None:
        if not self.strategy_enabled:
            return

        current_tick = self.flow.ticks_elapsed
        if (
            self._last_strategy_refresh_tick is not None
            and current_tick - self._last_strategy_refresh_tick < self.strategy_refresh_interval
        ):
            return

        mid_price = self.engine.mid()
        if mid_price is None:
            return

        bid_report, ask_report = self.market_maker.refresh(
            mid_price=mid_price,
            inventory=self.inventory,
            volatility=self.strategy_volatility,
            current_tick=current_tick,
        )

        self.my_orders.add(bid_report.order_id)
        self.my_orders.add(ask_report.order_id)
        self.strategy_order_ids.add(bid_report.order_id)
        self.strategy_order_ids.add(ask_report.order_id)
        self._last_strategy_refresh_tick = current_tick

        self._process_fills(bid_report.fills)
        self._process_fills(ask_report.fills)



    # ====== Inventory tracking methods ========

    # 1) updates inventory & cash according to buy / sell sign (pos / neg)
    def _apply_user_execution(self, side: Side, price: float, quantity: int) -> None: 
        signed_quantity = side.sign * quantity
        self.inventory += signed_quantity
        self.cash -= signed_quantity * price
        return None
    
    # 2) if incoming / resting order belongs to user, apply execution 
    def _account_for_fill(self, fill: Fill) -> None:
        incoming_order = self.engine.find_order(fill.incoming_id)
        if incoming_order is not None and incoming_order.actor == "user":
            self._apply_user_execution(
                side = incoming_order.side,
                price = fill.price,
                quantity = fill.quantity
            )

        resting_order = self.engine.find_order(fill.resting_id)

        if resting_order is not None and resting_order.actor == "user":
            self._apply_user_execution(
                side = resting_order.side,
                price = fill.price,
                quantity = fill.quantity
            )

    def _record(self, fills: list[Fill]) -> None:
        for fill in fills:
            print_data = {
                "at": strftime("%H:%M:%S"),
                "price": fill.price,
                "quantity": fill.quantity,
                "taker": fill.taker_side.value,
            }
            self.prints.appendleft(print_data)
            self.last_print = fill.price

    # returns dictionary of portfolio consisting in:  initial cash, cash, inventory, mark price, inventory value, equity, pnl
    def portfolio_snapshot(self):
        # mark price
        mark_price = self.anchor_price()

        # inventory value
        inventory_value = self.inventory * mark_price

        # equity
        equity = self.cash + inventory_value

        # total mark to market p&l (profit and loss)
        pnl = equity - self.initial_cash

        return {
            "initial_cash": self.initial_cash,
            "cash": self.cash,
            "inventory": self.inventory,
            "mark_price": mark_price,
            "inventory_value": inventory_value,
            "equity": equity,
            "pnl": pnl
        }
            

    def advance(self, ticks: int=1) -> None:
        if not self.live:
            return

        fills = self.flow.advance(ticks)
        self._process_fills(fills)
        self._refresh_strategy()

    
    def restart(self) -> None:
        self.engine.reset()
        self.flow = FlowGenerator(
            self.engine,
            FlowSettings(seed=self.flow.settings.seed)
        )
        self.market_maker.cancel_active_quotes()
        self.strategy_enabled = False
        self._last_strategy_refresh_tick = None
        self.strategy_order_ids.clear()
        self.market_maker.active_ask_id = None
        self.market_maker.active_bid_id = None
        self.market_maker.last_quote = None
        self.prints.clear()
        self.my_orders.clear()
        self.last_print = None
        self.cash = self.initial_cash
        self.inventory = 0
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

            return BandVerdict(
                within=False,
                price=ceiling,
                reason=(f"BID at {price:,.2f} 는 시장가보다 {pct_above:,.0f}% 더 높습니다. 주문은 ceiling 값인 {ceiling:,.2f} 으로 고정됩니다."),
            )

        if side is Side.ASK and price < floor:
            pct_below = (1 - price / ref) * 100
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
        
        self._process_fills(report.fills)

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

        return True

    def cancellation_error(self, order_id: int) -> str | None:
        """Explain why a user order cannot be cancelled, if applicable."""
        if order_id not in self.my_orders:
            return "order not found or not yours"

        order = self.engine.find_order(order_id)
        if order is None:
            return "order not found"
        if self.engine.find(order_id) is None:
            return f"order is already {order.status.value}"
        return None
    
    
    def snapshot(self, depth: int = 10) -> dict:
        
        best_bid = self.engine.best_bid()
        best_ask = self.engine.best_ask()
        mid = self.engine.mid()
        spread = self.engine.spread()

        bids = self.engine.ladder(Side.BID, depth)
        asks = self.engine.ladder(Side.ASK, depth)

        user_orders = []
        for order_id in sorted(self.my_orders, reverse=True):
            order = self.engine.find_order(order_id)
            if order is None:
                continue
            user_orders.append({
                "order_id": order.order_id,
                "side": order.side.value,
                "order_type": order.order_type.value,
                "original_quantity": order.original_qty,
                "filled_quantity": order.filled_qty,
                "open_quantity": order.open_qty,
                "quantity": order.open_qty,
                "status": order.status.value,
                "source": (
                    "strategy"
                    if order.order_id in self.strategy_order_ids
                    else "manual"
                ),
                "price": (
                    self.engine.scale.to_price(order.limit_ticks)
                    if order.limit_ticks is not None else None
                ),
            })

        active_orders = [
            order for order in user_orders
            if self.engine.find(order["order_id"]) is not None
        ]
        finished_orders = [
            order for order in user_orders
            if self.engine.find(order["order_id"]) is None
        ]
        
        strategy_quote = self.market_maker.last_quote

        return {
            "live": self.live,
            "tempo": self.tempo,
            "urgency": self.flow.settings.urgency,

            "clock": {
                "ticks": self.flow.ticks_elapsed,
            },

            "portfolio": self.portfolio_snapshot(),

            "top": {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid": mid,
                "spread": spread,
                "fair_value": self.flow.fair_value.value,
                "last_print": self.last_print,
            },

            "strategy": {
                "enabled": self.strategy_enabled,
                "volatility": self.strategy_volatility,
                "risk_aversion": self.market_maker.parameters.risk_aversion,
                "kappa": self.market_maker.parameters.kappa,
                "order_quantity": self.market_maker.order_quantity,
                "target_inventory": self.market_maker.parameters.target_inventory,
                "refresh_interval": self.strategy_refresh_interval,
                "total_ticks": self.market_maker.total_ticks,
                "remaining_time": self.market_maker.remaining_time(self.flow.ticks_elapsed),
                "active_bid_id": self.market_maker.active_bid_id,
                "active_ask_id": self.market_maker.active_ask_id,
                "bid_price": (
                    strategy_quote.bid_price
                    if strategy_quote is not None
                    else None
                ),
                "ask_price": (
                    strategy_quote.ask_price
                    if strategy_quote is not None
                    else None
                ),
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

        "my_orders": user_orders,
        "my_active_orders": active_orders,
        "my_finished_orders": finished_orders,
    }
