from __future__ import annotations
from matching import Fill, Side, MatchingEngine
import random
from dataclasses import dataclass, field
import math
from typing import Protocol

@dataclass
class FlowSettings:
    anchor: float = 100.0 # fair_value
    tick_size: float = 0.01

    drift: float = 0.0 # drift
    vol: float = 0.05 # sigma

    # Flow intensities
    quote_intensity: float = 6.0    # limit rate
    take_intensity: float = 1.2     # markeet rate
    pull_intensity: float = 3.0     # cancel rate

    
    mean_distance_ticks: float = 8.0
    cross_probability: float = 0.15

    # order sizes
    lot_min: float = 1
    lot_max: float = 12

    # aggressiveness
    urgency: float = 1.0
    seed: int | None = None

# poisson distribution is used for deciding how many quotes arrive this tick
def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0: return 0
    # Knuth's algorithm
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k -1 
            
class FairValue:
    def __init__(
            self, 
            anchor: float, # fair value
            drift: float, 
            vol: float, 
            rng:random.Random) -> None:
        self.value = anchor
        self.drift = drift 
        self.vol = vol
        self.rng = rng # random number generator

    def advance(self) -> float:
        self.value = max(0.01, self.value + self.drift + self.rng.gauss(0, self.vol))
        return self.value

class Agent(Protocol): 
    def act(self, ctx: "FlowGenerator") -> list[Fill]: ...

class QuotePoster:
    def act(self, ctx: "FlowGenerator") -> list[Fill]:
        """
        decide how many new quotes arrive O
        -> choose bid / ask O
        -> choose where to place them O
        -> choose size 
        -> send them to MatchingEngine
        -> remember any order that stays resting
        -> return any fills that happened
        """
        settings = ctx.settings

        trades: list[Fill] = []

        n = poisson(ctx.rng, settings.quote_intensity)
        tick = settings.tick_size

        # choosing the side
        for _ in range(n):
            side = ctx.rng.choice((Side.BID, Side.ASK))
            distance = ctx.rng.expovariate(1/ settings.mean_distance_ticks)
            crosses = ctx.rng.random() < ctx.settings.cross_probability

            # price should be calculated here
            quantity = ctx.lot()
            report = ctx.engine.place_limit(side, price, quantity)
            
            sign = -1.0 if crosses else 1.0
            price = ctx.fair_value.advance()
            

        return
    
class LiquidityTaker:
    def act(self, ctx) -> list[Fill]:
        return
    

class QuotePuller:
    def act(self, ctx) -> list[Fill]:
        return


class FlowGenerator:
    def __init__(self, engine: MatchingEngine, settings: FlowSettings | None = None) -> None:
        self.engine = engine
        self.settings = settings if settings is not None else  FlowSettings()
        self.rng = random.Random(self.settings.seed)
        self.fair_value = FairValue(
            settings.anchor, 
            settings.drift, 
            settings.vol, 
            self.rng)
        self.owned: set[int] = set()
        self.agents: list[Agent] = [QuotePuller(), QuotePoster(), LiquidityTaker()]
        self.ticks_elapsed = 0
    
    def lot(self, scale: float = 1.0) -> int:
        return
    
    def prime(self) -> None:
        return
    
    def advance(self, ticks: int=1) -> list[Fill]: 
        return
