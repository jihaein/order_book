from matching import MatchingEngine, TickScale, Fill, Side, OrderType, OrderStatus
from flow import FlowGenerator, FlowSettings
from collections import deque
from time import strftime
from dataclasses import dataclass, field
from strategies.avellaneda_stoikov import ASParameters
from strategies.as_market_maker import ASMarketMaker
from replay import MarketDataReplay

@dataclass(frozen=True)
class BandVerdict:
    within: bool
    price: float
    reason: str = ""


@dataclass(frozen=True)
class TradingRules:
    max_order_quantity: int = 2_000
    inventory_limit: int = 100
    fee_rate: float = 0.00003
    contract_multiplier: int = 250_000
    initial_margin_rate: float = 0.2175
    maintenance_margin_rate: float = 0.145

class MarketSession:
    def __init__(self, scale: TickScale | None = None, seed: int | None = None, initial_cash: float = 1_000_000_000.0) -> None:
        self.engine = MatchingEngine(scale)
        self.synthetic_seed = seed
        self.flow = FlowGenerator(self.engine, FlowSettings(seed=seed))
        self.source_mode = "synthetic"
        self.replay_orderbook_path = None
        self.replay_trades_path = None
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
        self.rules = TradingRules()
        self.fees_paid = 0.0

        # AS Model
        self.strategy_enabled = False
        self.strategy_volatility = 0.05
        self.strategy_refresh_interval = 10
        self.strategy_fair_value_source = "mid"
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

        reference_price = self.strategy_reference_price()
        if reference_price is None:
            return

        bid_quantity = min(
            self.market_maker.order_quantity,
            max(0, self.rules.inventory_limit - self.inventory),
        )
        ask_quantity = min(
            self.market_maker.order_quantity,
            max(0, self.rules.inventory_limit + self.inventory),
        )

        bid_report, ask_report = self.market_maker.refresh(
            mid_price=reference_price,
            inventory=self.inventory,
            volatility=self.strategy_volatility,
            current_tick=current_tick,
            bid_quantity=bid_quantity,
            ask_quantity=ask_quantity,
        )

        for report in (bid_report, ask_report):
            if report is None:
                continue
            self.my_orders.add(report.order_id)
            self.strategy_order_ids.add(report.order_id)
            if hasattr(self.flow, "register_shadow_order"):
                self.flow.register_shadow_order(report.order_id)
        self._last_strategy_refresh_tick = current_tick

        self._process_fills(bid_report.fills if bid_report is not None else [])
        self._process_fills(ask_report.fills if ask_report is not None else [])



    # ====== Inventory tracking methods ========

    # 1) updates inventory & cash according to buy / sell sign (pos / neg)
    def _apply_user_execution(self, side: Side, price: float, quantity: int) -> None: 
        signed_quantity = side.sign * quantity
        self.inventory += signed_quantity
        traded_notional = price * quantity * self.rules.contract_multiplier
        fee = traded_notional * self.rules.fee_rate
        self.cash -= signed_quantity * price * self.rules.contract_multiplier + fee
        self.fees_paid += fee
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
        inventory_value = self.inventory * mark_price * self.rules.contract_multiplier

        # equity
        equity = self.cash + inventory_value

        # total mark to market p&l (profit and loss)
        pnl = equity - self.initial_cash
        position_notional = abs(inventory_value)
        initial_margin = position_notional * self.rules.initial_margin_rate
        maintenance_margin = position_notional * self.rules.maintenance_margin_rate

        return {
            "initial_cash": self.initial_cash,
            "cash": self.cash,
            "inventory": self.inventory,
            "mark_price": mark_price,
            "inventory_value": inventory_value,
            "equity": equity,
            "pnl": pnl,
            "fees_paid": self.fees_paid,
            "position_notional": position_notional,
            "initial_margin": initial_margin,
            "maintenance_margin": maintenance_margin,
            "margin_excess": equity - initial_margin,
            "margin_status": "ok" if equity >= maintenance_margin else "margin_call",
            "currency": "KRW",
            "contract_multiplier": self.rules.contract_multiplier,
        }
            

    def advance(self, ticks: int=1) -> None:
        if not self.live:
            return

        fills = self.flow.advance(ticks)
        self._process_fills(fills)
        self._refresh_strategy()
        if getattr(self.flow, "finished", False):
            self.live = False

    def _reset_session_state(self) -> None:
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
        self.fees_paid = 0.0

    def load_replay(self, orderbook_path, trades_path=None) -> None:
        if hasattr(self.flow, "close"):
            self.flow.close()
        self.market_maker.cancel_active_quotes()
        self.engine.reset()
        self.source_mode = "replay"
        self.replay_orderbook_path = orderbook_path
        self.replay_trades_path = trades_path
        self.flow = MarketDataReplay(self.engine, orderbook_path, trades_path)
        self.live = False
        self._reset_session_state()
        fills = self.flow.advance()
        self._process_fills(fills)

    def load_synthetic(self) -> None:
        if hasattr(self.flow, "close"):
            self.flow.close()
        self.market_maker.cancel_active_quotes()
        self.engine.reset()
        self.source_mode = "synthetic"
        self.replay_orderbook_path = None
        self.replay_trades_path = None
        self.flow = FlowGenerator(
            self.engine,
            FlowSettings(seed=self.synthetic_seed),
        )
        self.live = False
        self._reset_session_state()
        fills = self.flow.advance()
        self._process_fills(fills)

    def restart(self) -> None:
        if hasattr(self.flow, "close"):
            self.flow.close()
        self.market_maker.cancel_active_quotes()
        self.engine.reset()
        if self.source_mode == "replay" and self.replay_orderbook_path is not None:
            self.flow = MarketDataReplay(
                self.engine,
                self.replay_orderbook_path,
                self.replay_trades_path,
            )
        else:
            self.flow = FlowGenerator(
                self.engine,
                FlowSettings(seed=self.synthetic_seed)
            )
        self.live = False
        self._reset_session_state()
        self.fees_paid = 0.0
        fills = self.flow.advance()
        self._process_fills(fills)
    
    
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

    def microprice(self) -> float | None:
        if self.source_mode == "replay" and hasattr(self.flow, "market_microprice"):
            return self.flow.market_microprice()
        bids = self.engine.ladder(Side.BID, 1)
        asks = self.engine.ladder(Side.ASK, 1)
        if not bids or not asks:
            return None
        bid_price, bid_quantity = bids[0]
        ask_price, ask_quantity = asks[0]
        total_quantity = bid_quantity + ask_quantity
        if total_quantity <= 0:
            return None
        return (
            ask_price * bid_quantity + bid_price * ask_quantity
        ) / total_quantity

    def strategy_reference_price(self) -> float | None:
        if self.strategy_fair_value_source == "micro":
            return self.microprice()
        if self.strategy_fair_value_source == "theoretical":
            return self.flow.fair_value.value
        if self.source_mode == "replay":
            if self.flow.market_best_bid is None or self.flow.market_best_ask is None:
                return None
            return (self.flow.market_best_bid + self.flow.market_best_ask) / 2
        return self.engine.mid()

    def configure_strategy(
        self,
        fair_value_source: str | None = None,
        risk_aversion: float | None = None,
        kappa: float | None = None,
        order_quantity: int | None = None,
    ) -> None:
        if fair_value_source is not None:
            if fair_value_source not in {"mid", "micro", "theoretical"}:
                raise ValueError("fair_value_source must be mid, micro, or theoretical")
            self.strategy_fair_value_source = fair_value_source
        if risk_aversion is not None or kappa is not None:
            self.market_maker.parameters = ASParameters(
                risk_aversion=(
                    risk_aversion
                    if risk_aversion is not None
                    else self.market_maker.parameters.risk_aversion
                ),
                kappa=(
                    kappa
                    if kappa is not None
                    else self.market_maker.parameters.kappa
                ),
                target_inventory=self.market_maker.parameters.target_inventory,
            )
        if order_quantity is not None:
            if order_quantity > self.rules.max_order_quantity:
                raise ValueError("order quantity exceeds the per-order limit")
            self.market_maker.order_quantity = order_quantity
    
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
        if quantity > self.rules.max_order_quantity:
            return {
                "outcome": "rejected",
                "reason": f"1회 주문 수량은 {self.rules.max_order_quantity:,}개를 초과할 수 없습니다.",
            }
        inventory_headroom = (
            self.rules.inventory_limit - self.inventory
            if side is Side.BID
            else self.rules.inventory_limit + self.inventory
        )
        if quantity > inventory_headroom:
            return {
                "outcome": "rejected",
                "reason": (
                    f"포지션 한도 ±{self.rules.inventory_limit}을 초과합니다. "
                    f"현재 재고 {self.inventory}, 최대 가능 수량 {max(0, inventory_headroom)}."
                ),
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
            
            if not self.engine.scale.is_aligned(price):
                return {
                    "outcome": "rejected",
                    "reason": (f"Price must be a multiple of "
                               f"{self.engine.scale.size:.2f}."),
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
        if hasattr(self.flow, "register_shadow_order"):
            self.flow.register_shadow_order(report.order_id)

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
        
        if self.source_mode == "replay":
            best_bid = self.flow.market_best_bid
            best_ask = self.flow.market_best_ask
            mid = (
                (best_bid + best_ask) / 2
                if best_bid is not None and best_ask is not None else None
            )
            spread = (
                round(best_ask - best_bid, 10)
                if best_bid is not None and best_ask is not None else None
            )
        else:
            best_bid = self.engine.best_bid()
            best_ask = self.engine.best_ask()
            mid = self.engine.mid()
            spread = self.engine.spread()
        market_last = (
            getattr(self.flow, "last_price", None)
            if self.source_mode == "replay"
            else self.last_print
        )

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
                "timestamp": getattr(self.flow, "current_timestamp", None),
            },

            "source": {
                "mode": self.source_mode,
                "orderbook_file": (
                    self.replay_orderbook_path.name
                    if self.replay_orderbook_path is not None else None
                ),
                "trades_file": (
                    self.replay_trades_path.name
                    if self.replay_trades_path is not None else None
                ),
                "finished": getattr(self.flow, "finished", False),
            },

            "portfolio": self.portfolio_snapshot(),

            "top": {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid": mid,
                "spread": spread,
                "fair_value": self.flow.fair_value.value,
                "last_print": market_last,
            },

            "strategy": {
                "enabled": self.strategy_enabled,
                "volatility": self.strategy_volatility,
                "risk_aversion": self.market_maker.parameters.risk_aversion,
                "kappa": self.market_maker.parameters.kappa,
                "order_quantity": self.market_maker.order_quantity,
                "target_inventory": self.market_maker.parameters.target_inventory,
                "fair_value_source": self.strategy_fair_value_source,
                "reference_price": self.strategy_reference_price(),
                "refresh_interval": self.strategy_refresh_interval,
                "total_ticks": self.market_maker.total_ticks,
                "remaining_time": self.market_maker.remaining_time(self.flow.ticks_elapsed),
                "active_bid_id": self.market_maker.active_bid_id,
                "active_ask_id": self.market_maker.active_ask_id,
                "bid_price": (
                    strategy_quote.bid_price
                    if strategy_quote is not None and self.market_maker.active_bid_id is not None
                    else None
                ),
                "ask_price": (
                    strategy_quote.ask_price
                    if strategy_quote is not None and self.market_maker.active_ask_id is not None
                    else None
                ),
            },

            "rules": {
                "max_order_quantity": self.rules.max_order_quantity,
                "inventory_limit": self.rules.inventory_limit,
                "fee_rate": self.rules.fee_rate,
                "contract_multiplier": self.rules.contract_multiplier,
                "initial_margin_rate": self.rules.initial_margin_rate,
                "maintenance_margin_rate": self.rules.maintenance_margin_rate,
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
