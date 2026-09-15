from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from market_session import MarketSession
from matching import OrderType, Side

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Orderbook")
session = MarketSession(seed=3)


class ConfigureBody(BaseModel):
    live: bool | None = None
    tempo: int | None = Field(default=None, ge=1, le=20)
    urgency: int | None = Field(default=None, ge=0, le=5)


class AdvanceBody(BaseModel):
    ticks: int = Field(default=1, ge=1, le=100)


class SubmitBody(BaseModel):
    side: str
    order_type: str
    quantity: int = Field(ge=1)
    price: float | None = None
    acknowledged: bool = False


def _parse_side(value: str) -> Side:
    try:
        return Side(value.lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="side must be 'bid' or 'ask'") from exc


def _parse_order_type(value: str) -> OrderType:
    try:
        return OrderType(value.lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="order_type must be 'limit' or 'market'",
        ) from exc


@app.get("/api/snapshot")
def snapshot(depth: int = 10) -> dict:
    depth = max(1, min(depth, 50))
    return session.snapshot(depth=depth)


@app.post("/api/configure")
def configure(body: ConfigureBody) -> dict:
    session.configure(live=body.live, tempo=body.tempo, urgency=body.urgency)
    return {"ok": True}


@app.post("/api/advance")
def advance(body: AdvanceBody) -> dict:
    session.advance(body.ticks)
    return {"ok": True}


@app.post("/api/restart")
def restart() -> dict:
    session.restart()
    return {"ok": True}


@app.post("/api/submit")
def submit(body: SubmitBody) -> dict:
    result = session.submit(
        _parse_side(body.side),
        _parse_order_type(body.order_type),
        body.quantity,
        price=body.price,
        acknowledged=body.acknowledged,
    )
    return result


@app.delete("/api/orders/{order_id}")
def cancel_order(order_id: int) -> dict:
    if not session.pull_mine(order_id):
        raise HTTPException(status_code=404, detail="order not found or not yours")
    return {"ok": True}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
