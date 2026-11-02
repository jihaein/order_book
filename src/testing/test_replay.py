import csv
import sys
import tempfile
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_session import MarketSession
from matching import OrderStatus, OrderType, Side


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_replay_uses_real_book_and_trade_feeds_read_only() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        quotes = root / "sample_011.csv"
        trades = root / "sample_010.csv"
        quote_rows = [
            {
                "received_at": "2026-01-01T09:00:00.000+09:00",
                "futs_bidp1": "99", "futs_askp1": "101",
                "bidp_rsqn1": "10", "askp_rsqn1": "12",
            },
            {
                "received_at": "2026-01-01T09:00:01.000+09:00",
                "futs_bidp1": "98", "futs_askp1": "99",
                "bidp_rsqn1": "11", "askp_rsqn1": "9",
            },
        ]
        trade_rows = [
            {
                "received_at": "2026-01-01T08:59:59.900+09:00",
                "futs_prpr": "100", "hts_thpr": "100.25", "last_cnqn": "1",
            },
            {
                "received_at": "2026-01-01T09:00:00.900+09:00",
                "futs_prpr": "98.5", "hts_thpr": "98.75", "last_cnqn": "20",
            },
        ]
        write_csv(quotes, quote_rows)
        write_csv(trades, trade_rows)
        original_quotes = quotes.read_bytes()
        original_trades = trades.read_bytes()

        session = MarketSession(seed=1)
        session.load_replay(quotes, trades)
        first = session.snapshot()
        assert first["source"]["mode"] == "replay"
        assert first["clock"]["timestamp"] == quote_rows[0]["received_at"]
        assert first["top"]["best_bid"] == 99
        assert first["top"]["best_ask"] == 101
        assert first["top"]["fair_value"] == 100.25

        order = session.submit(Side.BID, OrderType.LIMIT, 1, price=100)
        session.configure(live=True)
        session.advance(1)
        historical = session.engine.find_order(order["order_id"])
        assert historical is not None
        assert historical.status is OrderStatus.FILLED
        assert session.inventory == 1
        assert session.snapshot()["top"]["last_print"] == 98.5
        assert quotes.read_bytes() == original_quotes
        assert trades.read_bytes() == original_trades

        session.load_synthetic()
        synthetic = session.snapshot()
        assert synthetic["source"]["mode"] == "synthetic"
        assert synthetic["source"]["orderbook_file"] is None
        assert synthetic["clock"]["timestamp"] is None
        assert synthetic["top"]["fair_value"] is not None


def test_passive_order_waits_for_recorded_queue_ahead() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        quotes = root / "queue_011.csv"
        trades = root / "queue_010.csv"
        quote_rows = [
            {
                "received_at": f"2026-01-01T09:00:0{second}.000+09:00",
                "futs_bidp1": "99", "futs_askp1": "101",
                "bidp_rsqn1": "10", "askp_rsqn1": "10",
            }
            for second in range(3)
        ]
        trade_rows = [
            {
                "received_at": "2026-01-01T08:59:59.900+09:00",
                "futs_prpr": "100", "hts_thpr": "100", "last_cnqn": "1",
            },
            {
                "received_at": "2026-01-01T09:00:00.900+09:00",
                "futs_prpr": "99", "hts_thpr": "100", "last_cnqn": "6",
            },
            {
                "received_at": "2026-01-01T09:00:01.900+09:00",
                "futs_prpr": "99", "hts_thpr": "100", "last_cnqn": "5",
            },
        ]
        write_csv(quotes, quote_rows)
        write_csv(trades, trade_rows)

        session = MarketSession(seed=1)
        session.load_replay(quotes, trades)
        result = session.submit(Side.BID, OrderType.LIMIT, 3, price=99)
        order_id = result["order_id"]
        session.configure(live=True)

        session.advance(1)
        assert session.engine.find_order(order_id).filled_qty == 0

        session.advance(1)
        order = session.engine.find_order(order_id)
        assert order.filled_qty == 1
        assert order.open_qty == 2
        assert session.inventory == 1


if __name__ == "__main__":
    for test in (
        test_replay_uses_real_book_and_trade_feeds_read_only,
        test_passive_order_waits_for_recorded_queue_ahead,
    ):
        test()
        print(f"PASS: {test.__name__}")
