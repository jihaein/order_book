from matching import Fill
import random
from dataclasses import dataclass, field
import math
from typing import Protocol

@dataclass
class FlowSettings:
    anchor: 100.0
    drift: 0.0
    vol: 0.05
    quote_intensity: 6.0
    take_intensity: 1.2
    pull_intensity: 3.0
    mean_distance_ticks: 8.0
    cross_probability: 0.15
    lot_min: 1
    lot_max: 12
    urgency: 1.0
    seed: None

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
            anchor: float, 
            drift: float, 
            vol: float, 
            rng:random.Random) -> None:
        self.value = anchor
        self.drift = drift 
        self.vol = vol
        self.rng = rng # random number generator

    def advance(self) -> float:
        self.value = max(0.01, self.value + self.drift + self.rng.gauss(0, self.vol))

class Agent(Protocol): 
    def act(self, ctx: "FlowGenerator") -> list[Fill]: ...


class QuotePoster:
    def act(self, ctx) -> list[Fill]:
        return
    

class FlowGenerator:
    def __init__(self):
        return
