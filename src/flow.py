from __future__ import annotations
from matching import Fill, Side, MatchingEngine, BookSide, Order
import random
from dataclasses import dataclass, field
import math
from typing import Protocol

# DISCLAIMER: Market Simulation logic is originally built by @romanmichaelpaolucci
# variables and functions are added/altered to improve compatibility with matching.py

@dataclass
class FlowSettings:
    anchor: float = 100.0 # fair_value
    tick_size: float = 0.01

    drift: float = 0.0 # driftd
    vol: float = 0.05 # sigma

    # Flow intensities
    quote_intensity: float = 6.0    # limit rate
    take_intensity: float = 1.2     # markeet rate
    pull_intensity: float = 3.0     # cancel rate

    
    mean_distance_ticks: float = 8.0
    cross_probability: float = 0.15

    # order sizes
    lot_min: int = 1
    lot_max: int = 12

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

#  agent places LO
class QuotePoster:
    def act(self, ctx: "FlowGenerator") -> list[Fill]:
        """
        decide how many new quotes arrive O
        -> choose bid / ask O
        -> choose where to place them O
        -> choose size 
        -> send them to MatchingEngine
        -> remember any order that stays resting
        -> return fills that happened
        """
        settings = ctx.settings

        trades: list[Fill] = []

        n = poisson(ctx.rng, settings.quote_intensity)
        tick = settings.tick_size
 
        # choosing the side
        for _ in range(n):
            side = ctx.rng.choice((Side.BID, Side.ASK))
            distance = ctx.rng.expovariate(1/ settings.mean_distance_ticks)
            crosses = (ctx.rng.random() < ctx.settings.cross_probability)
            quantity = ctx.lot()

            # price calculation only happens when bid and ask crosses
            fair = ctx.fair_value.value 
            if crosses: 
                if side == Side.BID:
                    price = fair + distance * tick
                else:
                    price = fair - distance * tick
            else:
                if side == Side.BID:
                    price = fair - distance * tick
                else:
                    price = fair + distance * tick

            report = ctx.engine.place_limit(side, price, quantity)
            trades.extend(report.fills)

            if report.open_qty > 0:
                ctx.owned.add(report.order_id)

        return trades
    
#  agent places MO
class LiquidityTaker:
    def act(self, ctx: "FlowGenerator") -> list[Fill]:

        settings = ctx.settings
        trades: list[Fill] = []

        n = poisson(ctx.rng, settings.take_intensity)
        
        for _ in range (n):
            side = ctx.rng.choice((Side.BID, Side.ASK))
            # only send if there is cross
            opposite_best = ctx.engine.best_ask() if side is Side.BID else ctx.engine.best_bid()
            if opposite_best is None:
                continue
            quantity = ctx.lot()
            
            report = ctx.engine.place_market(side, quantity)
            trades.extend(report.fills)

        return trades
    
# agent cancels LO 
class QuotePuller:
    def act(self, ctx: "FlowGenerator") -> list[Fill]:
        settings = ctx.settings
        n = poisson(ctx.rng, settings.pull_intensity)
        for _ in range(n):
            if not ctx.owned:
                break 
            oid = ctx.rng.choice(tuple(ctx.owned))
            ctx.owned.discard(oid)
            ctx.engine.pull(oid)
        return []
    
# 1 step -> 3 agents places each order
class FlowGenerator:
    def __init__(self, engine: MatchingEngine, settings: FlowSettings | None = None) -> None:
        self.engine = engine
        self.settings = settings if settings is not None else FlowSettings()
        self.rng = random.Random(self.settings.seed)
        self.fair_value = FairValue(
            self.settings.anchor, 
            self.settings.drift, 
            self.settings.vol, 
            self.rng)
        self.owned: set[int] = set()
        self.agents: list[Agent] = [QuotePuller(), QuotePoster(), LiquidityTaker()]
        self.ticks_elapsed = 0
    
    def lot(self, scale: float = 1.0) -> int:
        return max(1, round( self.rng.randint( self.settings.lot_min, self.settings.lot_max,) * scale))
        
    def advance(self, ticks: int=1) -> list[Fill]:
        trades: list[Fill] = []
        for _ in range(ticks):
            self.fair_value.advance()
            for agent in self.agents:
                trades.extend(agent.act(self))
            self.ticks_elapsed += 1
        return trades
    
    
