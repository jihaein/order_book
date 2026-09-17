# OrderBook Market Microstructure Simulator 
A python-based market microstructure simulator featuring limit order book.

### Project Goal

The goal of this project is to build a simplified exchange environment from scratch and use it to study how different market making strategies behave and to compare the profit generating functions.

Current features are:
- limit order book 
- price then time priority matching
- limit order & market order
- partial fills & LO cancellation
- random walk fair value
- price band protection for fat-finger / aggressive limit orders
- market agents

Upcoming plans:
- avellaneda stoikov market maker 
- strategy comparison 
- market makign performance analysis / comparison

### Project Structure

#### matching.py
This engine implements price-time priority. 

- **price priority**: The more aggressive, the higher price for bid. Vice versa for ask. The best available price is always matched first
- **Time Priority**: FIFO queue
- **Limit order** consists of quantity and buying/selling price. If the order crosses the opposite book, it is exectued immediately. Otherwise, rests in the orderbook.
- **market order** immediately trades against the best available bid/ask.

Market Agents
- **QuotePoster**: submits limit orders around the fv. (the number of quotes is sampled from a Poisson distribution)
- **LiquidityTaker**: submits market orders only
- **QuotePuller** : cancels limit orders

Fair Value (FV)
- random walk used for simulating fair value: S(t+1) = S(t) + drift + noise.

DISCLAIMER: I implemented @romanmichaelpaolucci's market_sim.py algorithm into my project (flow.py simulation)

matching.py
- Side
- OrderType
- OrderStatus
- TickScale
- Order
- Fill
- ExecutionReport
- RestingQueue
- BookSide
- MatchingEngine

flow.py
- FlowSettings
- FairValue
- Agent
- QuotePoster
- LiquidityTaker
- QuotePuller
- FlowGenerator 

market_session.py
- BandVerdict
- MarketSession

DISCLAIMER: Frontend design is entirely AI generated.

### Running the Project

Activate the virtual environment: 
```bash
source .venv/bin/activate
```

Start the server:
```bash
PYTHONPATH=src uvicorn server:app --reload
```
