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

From the `orderbook` directory, activate the virtual environment:
```bash
source .venv/bin/activate
```

Start the application:
```bash
python src/app.py
```

Then open http://127.0.0.1:8000 in your browser.

If port 8000 is already in use, the server is probably already running. Try
opening the URL before starting another server.

For automatic reload during development, use:
```bash
PYTHONPATH=src uvicorn server:app --reload
```

Do not open `src/static/index.html` directly with a `file://` URL. The page
needs the local API server. The former Streamlit interface has been removed so
all supported launch commands now use the same frontend.

You can also double-click `start.command` in Finder. It starts the local server
if needed and opens the app. Server output is stored in `logs/app.log`.

### Collecting KOSPI 200 Futures Data

`src/ws_test.py` collects two KIS real-time feeds:

- 010: index futures trades
- 011: index futures order book quotes

It uses the KIS helpers in the sibling `open-trading-api` repository. If it is
missing, clone it beside this repository:

```bash
cd ..
git clone https://github.com/koreainvestment/open-trading-api.git
cd orderbook
```

From the `orderbook` directory, run:
```bash
python src/ws_test.py
```

For a full session on macOS, use:
```bash
caffeinate -i python src/ws_test.py
```

The files are saved:

```text
data/YYYYMMDD_010.csv
data/YYYYMMDD_011.csv
```

To check that collection is working, run this in another terminal:

```bash
ls -lh data
wc -l data/YYYYMMDD_010.csv
wc -l data/YYYYMMDD_011.csv
```

031 is left out for now because KIS documents it as a stock futures feed, while this script is collecting KOSPI 200 index futures.
