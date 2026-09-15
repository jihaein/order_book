from matching import MatchingEngine, TickScale, Fill
from flow import FlowGenerator, FlowSettings
from collections import deque
from time import strftime

class MarketSession:
    def __init__(self, scale: TickScale | None = None, seed: int | None = None) -> None:
        self.engine = MatchingEngine(scale)
        self.flow = FlowGenerator(self.engine, FlowSettings(seed=seed))
        self.live: bool = False
        self.tempo: int = 4
        PRINT_HISTORY = 100
        self.prints = deque(maxlen=PRINT_HISTORY)
        self.my_orders: set[int]
        self.last_print: float | None
        self.flow.advance()


    def _record(self, fills: list[Fill]) -> None:
        record = {}
        for fill in fills:
            print_data = {
                "at": strftime("%H:%M:%S"),
                "price": fills.price,
                "quantity": fills.quantity,
                "taker": fills.taker.value,
            }

            self.prints.appendleft(print_data)
            self.last_print = print_data

    def advance(self, ticks: int=1) -> None:
        return
    
    def restart(self) -> None:
        return
    
    def configure(self, live=None, tempo=None, urgency=None) -> None:
        return