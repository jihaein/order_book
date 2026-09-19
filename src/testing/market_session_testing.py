import json
from market_session import MarketSession
from matching import Side, OrderType

s = MarketSession(seed=3)
s.live = True
s.advance(50)

print(json.dumps(s.snapshot(), indent=2)[:700])

# the band, all three directions
print(s.submit(Side.BID, OrderType.LIMIT, 5, price=100000))
# -> outcome "needs_acknowledgement", collared_price near ref * 1.10

print(s.submit(Side.BID, OrderType.LIMIT, 5, price=100000, acknowledged=True))
# -> outcome "accepted", and it filled/rested at the COLLARED price

print(s.submit(Side.BID, OrderType.LIMIT, 5, price=50))
# -> outcome "accepted" — passive, far below the market, harmless. It rests.
