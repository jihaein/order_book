"""
=== Reservation Price ===
    mid-price -> current market midpoint
    inventory -> how many shares the strategy holds
    volatility -> how much the price moves
    risk aversion -> how strongly it reacts to inventory risk
    kappa -> how quickly does fill probability decline when my quote moves away from the market
    remaining time -> how much of the session remains

<calculation>
remaining_time = (
    total_ticks - current_tick
) / total_ticks


=== Optimal Spread ===

<calculation>
spread = (
    risk_aversion
    * volatility**2
    * remaining_time
    + (2 / risk_aversion)
    * log(1 + risk_aversion / kappa)
)

bid_price = reservation_price - spread / 2
ask_price = reservation_price + spread / 2
ask_price - bid_price = spread

=== Expected Outputs ===
    reservation price
    total spread
    bid price
    ask price

=== Example ===

Suppose:
mid_price       = 100
inventory       = 5
risk_aversion   = 0.1
volatility      = 1
remaining_time  = 1
kappa           = 1.5


Reservation price (r) = 100 - (5)(0.1)(1^2)(1) = 99.50 
Spread = 1.39
half spread = 0.695
bid = 99.50 - 0.695 = 98.805
ask = 99.50 + 0.695 = 100.195

after converting to valid ticks:
Bid: 98.80
Ask: 100.20
"""

from dataclasses import dataclass
from math import log1p

@dataclass(frozen=True)
class ASParameters:
    risk_aversion: float # gamma
    kappa: float # k (kappa)
    target_inventory: int = 0

@dataclass(frozen=True)
class ASQuote: 
    reservation_price: float
    spread: float
    bid_price: float
    ask_price: float


def calculate_quotes(
        mid_price: float, 
        inventory: int,
        volatility: float, 
        remaining_time: float,
        parameters: ASParameters,
) -> ASQuote:
    
    # input validation
    if mid_price <= 0:
        raise ValueError("mid_price 가 0보다 커야합니다.")
    if volatility < 0:
        raise ValueError ("volatility는 음수일 수 없습니다.")
    if parameters.risk_aversion <= 0:
        raise ValueError("risk aversion 은 0보다 커야합니다.")
    if parameters.kappa <= 0:
        raise ValueError("kappa 는 0보다 커야합니다.")
    if not 0 <= remaining_time <= 1:
        raise ValueError("remaining time 은 0에서 1사이의 값으로 표기되어야 합니다.")
    
    # inventory difference calculation
    inventory_gap = inventory - parameters.target_inventory

    # ==== quotes calculation =====

    # 1. reservation price
    reservation_price = mid_price - (inventory_gap * parameters.risk_aversion * (volatility ** 2) * remaining_time)

    # 2. total optimal spread
    spread = (
        parameters.risk_aversion 
        * (volatility ** 2) 
        * remaining_time 
        + (2 / parameters.risk_aversion) 
        * log1p(parameters.risk_aversion / parameters.kappa)
    )

    # 3. place bid and ask around the reservation price.
    half_spread = spread/2
    bid_price = reservation_price - half_spread
    ask_price = reservation_price + half_spread
    
    return ASQuote(
        reservation_price = reservation_price,
        spread = spread,
        bid_price = bid_price,
        ask_price = ask_price
    )