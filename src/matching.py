from __future__ import annotations
from enum import Enum 
from dataclasses import dataclass, field
from collections import OrderedDict
from sortedcontainers import SortedDict
from typing import Protocol
from itertools import count
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
        return round(price * self.size, 2)
    
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
    incoming_id: int
    sequence: int  # 몇번째 fill 인지

