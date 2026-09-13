from __future__ import annotations
from enum import Enum 
from dataclasses import dataclass, field
from collections import OrderedDict
from sortedcontainers import SortedDict
from typing import Protocol
from itertools import count, islice
from typing import Iterable, Iterator, Optional

"""
For coworking developers, this is how you use the imported packages

# Basic Enumerations
class Colour(Enum):
    RED = "red"
    BLUE = "blue"

    @property
    def contra(self): 
        return Colour.BLUE if self is Colour.RED else Colour.RED

        
# Dataclasses
@dataclass  # side note: @dataclass(frozen=True) makes instances immutable
class Point:
    x: int
    y: int
    label: str = "origin" #default value 
    tags: list = field(default_factory=list) #mutable default! 

p = Point(3,4) # __init__ generated for you
print(p) #readable repr for free


# OrderedDict: FIFO structure (time based)
queue = OrderedDict()
queue[101] = "first order that arrived" 
queue[102] = "second"
queue[103] = "third"

# oldest item, without scanning: O(1)
oldest_id, oldest = next(iter(queue.items())) # (101, "first ...")

del queue[102] # pull a specific order by id  / time will be O(1)


# sortedDict: sorts based on key
levels = SortedDict()
levels[10002] = "ask level at 100.02"
levels[10000] = "bid level at 100.00"
levels[10003] = "ask level at 100.03"

levels.keys()[0] # 10000 -> smallest key, O(log L)
levels.keys()[-1] # 10003 -> largest key, O(log L)
list(levels.keys()) # [10000, 10002, 10003] -- always ordered
del levels[10002] # O(log L)

# DISCLAIMER: DO NOT USE FLOATS. Convert all to ticks (int)
ticks = int(round(price / tick_size)) # the key (100.02 -> 10002)
price = round(ticks * tick_size, 10) # for display (10002 -> 100.02)
"""

# Enumerations 
class Side(Enum):
    BID = "bid"
    ASK = "ask"

    @property
    def contra(self): 
        return Side.BID if self is Side.ASK else Side.ASK 
    
    # sign assign helper
    @property
    def sign(self):
        return 1 if self is Side.BID else -1
    

class OrderType(Enum):
    LIMIT = "limit"
    MARKET = "market"

class OrderStatus(Enum):
    FILLED = "filled"       # fully traded
    PARTIAL = "partial"     # some traded. remainder exists as resting
    RESTING = "resting"     # nothing traded (all rests)
    EXPIRED = "expired"     # market order that ran out of book (remainder discarded)
    REJECTED = "rejected"   # does NOT enter the book (error)


@dataclass(frozen=True)
class TickScale:
    size: float = 0.01

    def __post_init__(self): 
        if self.size <= 0:
            raise ValueError("size가 0보다 커야 합니다.")
    
    def to_ticks(self, price: float) -> int:
        return int(round(price / self.size))
    
    def to_price(self, price: float) -> float:
        return round(price * self.size, 10)
    
    def snap(self, price: float) -> float:
        return self.to_price(self.to_ticks(price))
    

@dataclass
class Order:
    order_id: int
    side: Side
    order_type: OrderType
    original_qty: int   #submitted size (static)
    open_qty: int       # unfilled size
    limit_ticks: int | None = None  # ticks / None only for market order
    arrival: int=0  # time tick (?)
    actor: str="flow"

    @property
    def filled_qty(self) -> int:
        return self.original_qty - self.open_qty
    
    # true if no remaining orders are left
    @property
    def is_done(self) -> bool:
        return self.open_qty <= 0
    
@dataclass(frozen=True)
class Fill:
    price: float    #resting order's price
    quantity: int
    taker_side: Side #side of the incoming order
    resting_id: int   
    incoming_id: int # matched order with the resting_id
    sequence: int  # 몇번째 fill 인지

@dataclass
class ExecutionReport:
    order_id: int
    status: OrderStatus 
    fills: list[Fill] # all trade related to this order
    filled_qty: int
    open_qty: int 
    resting_price: float | None

    @property 
    def notional(self) -> float: # total value traded
        return sum(f.price * f.quantity for f in self.fills)
    
    @property
    def average_price(self) -> float | None:
        return None if self.filled_qty == 0 else self.notional / self.filled_qty
    


class RestingQueue: 

    def __init__(self, ticks: int, price: float) -> None:
        self.ticks = ticks
        self.price = price
        # INTERNAL DATA!!!!!
        self._orders: OrderedDict[int, Order] = OrderedDict() 
        self._depth: int=0 # total remaining quantity at this price

    @property
    def depth(self) -> int:
        return self._depth # O(1)
    
    def head(self) -> Order | None : # keeps track of oldest order / O(1)
        if not self._orders:
            return None
        return next(iter(self._orders.values()))

    def __len__(self) -> int: 
        return len(self._orders)

    def __bool__(self) -> bool:
        return len(self._orders) > 0
    
    def orders(self) -> Iterator[Order]:
        yield from self._orders.values()

    def join(self, order: Order) -> None:
        self._orders[order.order_id] = order 
        self._depth += order.open_qty

    # trading against the oldest order
    def fill_head(self, quantity: int) -> tuple[Order, int]:
        if not self._orders:
            raise RuntimeError("Queue가 비었습니다.")
        order = self.head()
        filled = min(quantity, order.open_qty)
        order.open_qty -= filled
        self._depth -= filled

        # now the order has been fulfilled -> should be deleted
        if order.open_qty == 0:
            del self._orders[order.order_id]
        return order, filled
    
    # cancelling an order
    def withdraw(self, order_id: int) -> Order | None:
        order = self._orders.get(order_id)
        if order is None:
            return None
        self._depth -= order.open_qty
        del self._orders[order_id]
        return order
    


class BookSide:

    def __init__(self, side: Side, scale: TickScale) -> None:
        self.side = side
        self.scale = scale
        self._levels: SortedDict[int, RestingQueue] = SortedDict()
    
    @property
    def _best_index(self) -> int:
        # returns last key for bid (best bid => highest price)
        # returns first key for ask (best ask => lowest price)
        return -1 if self.side is Side.BID else 0

    # returns the most aggressive price level (as tick)
    def best_ticks(self) -> int | None:
        if not self._levels:
            return None
        return self._levels.keys()[self._best_index]
    
    # returns the most aggressive price level (as price)
    def best_price(self) -> float | None: 
        ticks = self.best_ticks()
        if ticks is None:  
            return None
        return self.scale.to_price(ticks)
    
    # RestingQueue at the best price 
    def top(self) -> RestingQueue | None: 
        if not self._levels: 
            return None
        return self._levels.values()[self._best_index]

    def __bool__(self) -> bool:
        return len(self._levels) > 0

    def accepts(self, incoming_ticks: int | None) -> bool:
        if not self: 
            return False
        # market order accepts any price 
        if incoming_ticks is None:
            return True
        best = self.best_ticks()
        # If this is ask book, incoming order must be bid
        if self.side is Side.ASK:
            return incoming_ticks >= best
        # if this is bid book, incoming order must be ask
        else: 
            return incoming_ticks <= best
    
    # fetch queue at ticks
    def level(self, ticks: int, create: bool = False) -> RestingQueue | None:
        level = self._levels.get(ticks)
        if level is not None:
            return level
        if not create:
            return None
        level = RestingQueue(ticks=ticks, price=self.scale.to_price(ticks))
        self._levels[ticks] = level
        return level
    
    # if the level at ticks exists, but no order exists, delete the key
    def discard_if_empty(self, ticks: int) -> None:
        level = self._levels.get(ticks) 
        if level is not None and not level: 
            del self._levels[ticks]


    # helper for yielding aggressive -> least aggressive for both BID and ASK
    def _levels_aggressive_first(self) -> Iterator[RestingQueue]:
        if self._best_index == -1:
            yield from reversed(self._levels.values())
        else:
            yield from self._levels.values()

    # orders most aggressive to least (bid: highest price / ask: lowest price)
    def ladder(self, depth: int | None = None) -> list[tuple[float, int]]:
        levels = self._levels_aggressive_first()
        if depth is not None: 
            levels = islice(levels, depth)
        return [(level.price, level.depth) for level in levels]
    
    # yields all resting order in (price, then time) order. (aggressive first)
    def resting(self) -> Iterator[Order]:
        for level in self._levels_aggressive_first():
            yield from level.orders()

    # sum of depths across all levels
    def open_interest(self) -> int:
        return sum(level.depth for level in self._levels.values())
    
    # drop every level
    def clear(self) -> None:
        self._levels.clear()


class MatchingEngine:
    
    def __init__(self, scale: TickScale | None = None) -> None:
        self.scale = scale or TickScale()
        self.bids = BookSide(Side.BID, self.scale)
        self.asks = BookSide(Side.ASK, self.scale)
        self._index: dict[int, Order] = {} # resting orders by id
        self._next_id = count(1)
        self._next_arrival = count(1)
        self._next_seq = count(1)

    def side(self, side: Side) -> BookSide:
        return self.bids if side is Side.BID else self.asks
    
    def best_bid(self) -> float | None:
        return self.bids.best_price()
    
    def best_ask(self) -> float | None:
        return self.asks.best_price()
    
    def spread(self) -> float | None:
        if self.best_bid() is None or self.best_ask() is None:
            return None
        return round((self.best_ask() - self.best_bid()), 10)
    
    def mid(self) -> float | None:
        if self.best_bid() is None or self.best_ask() is None:
            return None
        return round(((self.best_ask() + self.best_bid())/2), 10)
    
    # thin pass through to BookSide ladder
    def ladder(self, side: Side, depth: int | None = None) -> list[tuple[float, int]]:
        return self.side(side).ladder(depth)
    
    def find(self, order_id: int) -> Order | None:
        return self._index.get(order_id)
    
    def __contains__(self, order_id: int) -> bool:
        return self.find(order_id) is not None
    
    # also a thin pass through to BookSide 
    def resting_orders(self, side: Side) -> Iterator[Order]:
        return self.side(side).resting()
    
    def top_of_book(self, depth: int=10) -> dict:
        top = {
            "bids": self.ladder(Side.BID, depth),
            "asks": self.ladder(Side.ASK, depth), 
            "best_bid": self.best_bid(),
            "best_ask": self.best_ask(),
            "spread": self.spread(),
            "mid": self.mid()
        }
        return top
    
    def reset(self) -> None:
        self.bids.clear()
        self.asks.clear()
        self._index.clear()

    # placing limit order
    def place_limit(
            self, 
            side: Side, 
            price: float, 
            quantity: int, 
            actor: str="flow") -> ExecutionReport:
       
        if quantity <= 0: raise ValueError("quantity가 0보다 커야합니다.")

        """
        <ORDER CLASS REFERENCE>
        order_id: int
        side: Side
        order_type: OrderType
        original_qty: int   #submitted size (static)
        open_qty: int       # unfilled size
        limit_ticks: int | None = None  # ticks / None only for market order
        arrival: int=0  # time tick (?)
        actor: str="flow"
        """

        order = Order(
            order_id = next(self._next_id),
            side = side,
            order_type = OrderType.LIMIT,
            original_qty = quantity,
            open_qty = quantity,
            limit_ticks = self.scale.to_ticks(price), 
            arrival = next(self._next_arrival),
            actor=actor
        )

        """
        <EXECUTIONREPORT CLASS REFERENCE>
        order_id: int
        status: OrderStatus 
        fills: list[Fill] # all trade related to this order
        filled_qty: int
        open_qty: int 
        resting_price: float | None
        """

        fills = self._sweep(order)

        if not order.is_done:
            self._post(order)

        if order.open_qty == 0:
            status_er = OrderStatus.FILLED
        elif order.open_qty == order.original_qty:
            status_er = OrderStatus.RESTING
        else:
            status_er = OrderStatus.PARTIAL
        

        return ExecutionReport(
            order_id = order.order_id,
            status=status_er,
            fills = fills,
            filled_qty = order.filled_qty,
            open_qty = order.open_qty,
            resting_price=(
                self.scale.to_price(order.limit_ticks)
                if order.open_qty > 0
                else None
            )
        )
    
    # placing market order ( NO RESTING !!!)
    def place_market(
            self, 
            side: Side, 
            quantity: int, 
            actor: str="flow") -> ExecutionReport:
        if quantity <= 0: raise ValueError("quantity가 0보다 커야합니다.")

        order = Order(
        order_id = next(self._next_id),
        side = side,
        order_type = OrderType.MARKET,
        original_qty = quantity,
        open_qty = quantity,
        limit_ticks = None, 
        arrival = next(self._next_arrival),
        actor=actor)

        fills = self._sweep(order)

        if order.open_qty == 0:
            status_er = OrderStatus.FILLED
        else:
            status_er = OrderStatus.EXPIRED
        
        return ExecutionReport(
            order_id = order.order_id,
            status=status_er,
            fills= fills,
            filled_qty = order.filled_qty,
            open_qty = order.open_qty,
            resting_price= None
        )
    
    def _post(self, order: Order) -> None:
        book = self.side(order.side)
        level= book.level(order.limit_ticks, create=True)
        level.join(order)
        self._index[order.order_id] = order
    
    # cancelling a resting order (most likely by the trader ??)
    def pull(self, order_id: int) -> Order | None:
        order = self._index.pop(order_id, None)
        if order is None:
            return None
        book = self.side(order.side)
        level = book.level(order.limit_ticks)

        if level is not None:
            level.withdraw(order_id)
            book.discard_if_empty(order.limit_ticks)
        return order
    
    # takes incoming order and match with best bid/ask
    def _sweep(self, incoming: Order) -> list[Fill]:
        contra = self.side(incoming.side.contra)
        fills = []

        # while open quantity is left, keep trading
        while incoming.open_qty > 0 and contra:

            # price priority check first
            if not contra.accepts(incoming.limit_ticks):
                break # trade stops
            ticks = contra.best_ticks()
            level = contra.top()

            # time priority
            while incoming.open_qty > 0 and level:
                resting, qty = level.fill_head(incoming.open_qty)
                incoming.open_qty -= qty

                fills.append(Fill(
                    price = level.price,
                    quantity = qty,
                    taker_side = incoming.side,
                    resting_id = resting.order_id,
                    incoming_id = incoming.order_id,
                    sequence = next(self._next_seq)
                ))

                if resting.is_done:
                    self._index.pop(resting.order_id, None)

            contra.discard_if_empty(ticks)

        return fills






        