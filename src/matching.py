from __future__ import annotations
from enum import Enum 
from dataclasses import dataclass, field
from collections import OrderedDict
from sortedcontainers import SortedDict

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


# OrderedDict
queue = OrderedDict()
queue[101] = "first order that arrived" 
queue[102] = "second"
queue[103] = "third"

# oldest item, without scanning: O(1)
oldest_id, oldest = next(iter(queue.items())) # (101, "first ...")

del queue[102] # pull a specific order by id  / time will be O(1)
"""

