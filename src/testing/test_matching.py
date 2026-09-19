from matching import MatchingEngine, Side, OrderStatus

# SIMPLE TESTING ENGINE
match = MatchingEngine()
match.place_limit(Side.ASK, 100.02, 3)
match.place_limit(Side.ASK, 100.02, 5)
match.place_limit(Side.ASK, 100.03, 5)
match.place_limit(Side.BID, 100.00, 12)
match.place_limit(Side.BID, 99.99, 4)

print(match.best_bid(), match.best_ask(), match.spread(), match.mid())
# 100.0 100.02 0.02 100.01

# 1: the market bid for 10
rpt = match.place_market(Side.BID, 10)
for f in rpt.fills:
    print(f.quantity, "@", f.price)
# 3 @ 100.02 / 5 @ 100.02 / 2 @ 100.03

print(rpt.status, rpt.filled_qty, round(rpt.average_price, 3))
# OrderStatus.FILLED 10 100.022 
# REMEMBER: this is the slippage number!!!!!!

print(match.best_ask(), match.ladder(Side.ASK))
# 100.03 [(100.03, 3)]

#3: the marketable limit
rpt = match.place_limit(Side.BID, 100.05, 6)
print(rpt.status, rpt.filled_qty, rpt.open_qty, rpt.resting_price)
# OrderStatus.PARTIAL 3 3 100.05
print(match.best_bid())
# 100.05
