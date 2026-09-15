from matching import MatchingEngine, Side
from flow import FlowGenerator, FlowSettings

eng  = MatchingEngine()
flow = FlowGenerator(eng, FlowSettings(seed=7))

for i in range(500):
    flow.advance()
    bid, ask = eng.best_bid(), eng.best_ask()
    if bid is not None and ask is not None:
        assert bid < ask, f"crossed book at tick {i}: {bid} >= {ask}"

print(eng.best_bid(), eng.best_ask(), eng.spread())
print(eng.ladder(Side.BID, 5))
print(eng.ladder(Side.ASK, 5))
print(len(flow.owned), "quotes still owned")
