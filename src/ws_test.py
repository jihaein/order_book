import sys
import logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = REPO_ROOT.parent
KIS_REPO = PROJECT_ROOT / "open-trading-api"
EXAMPLES_USER = KIS_REPO / "examples_user"
FUTURES_EXAMPLES = EXAMPLES_USER / "domestic_futureoption"

sys.path.insert(0, str(EXAMPLES_USER))
sys.path.insert(0, str(FUTURES_EXAMPLES))

print("Current file:", CURRENT_FILE)
print("Project root:", PROJECT_ROOT)
print("KIS auth exists:", (EXAMPLES_USER / "kis_auth.py").exists())
print(
    "Futures functions exist:",
    (FUTURES_EXAMPLES / "domestic_futureoption_functions_ws.py").exists(),
)

import kis_auth as ka
from domestic_futureoption_functions_ws import (
    index_futures_realtime_conclusion,
    index_futures_realtime_quote,
)

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# KOSPI 200
FUTURES_CODE = "A01612"
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# mapping to documentation number instead of id
STREAM_NAMES = {
    "H0IFCNT0": "010",
    "H0IFASP0": "011",
}

def main():
    try:
        print("1. Starting REST authentication...", flush=True)
        ka.auth(svr="prod")
        print("2. REST authentication complete", flush=True)

        print("3. Starting WebSocket authentication...", flush=True)
        ka.auth_ws()
        print("4. WebSocket authentication complete", flush=True)

        print("5. Creating WebSocket client...", flush=True)
        kws = ka.KISWebSocket(api_url="/tryitout")

        print(
            f"6. Registering subscriptions for {FUTURES_CODE}...",
            flush=True,
        )

        kws.subscribe(
            request=index_futures_realtime_conclusion,
            data=[FUTURES_CODE],
        )

        kws.subscribe(
            request=index_futures_realtime_quote,
            data=[FUTURES_CODE],
        )

        print("7. Starting WebSocket — waiting for data...", flush=True)
        kws.start(on_result=on_result)

    except Exception:
        logger.exception("WebSocket collector failed")
        raise

def on_result(ws, tr_id, result, data_info):
    received_at = datetime.now(ZoneInfo("Asia/Seoul"))
    
    stream_name = STREAM_NAMES.get(tr_id)
    if stream_name is None:
        print("Unknown TR ID:", tr_id)
        return
    
    rows = result.copy()
    rows.insert(0, "received_at", received_at.isoformat(timespec="milliseconds"))

    date_text = received_at.strftime("%Y%m%d")
    output_file = DATA_DIR / f"{date_text}_{stream_name}_09_29.csv"

    write_header = not output_file.exists()

    rows.to_csv(
        output_file,
        mode="a",
        header=write_header,
        index=False
    )
    print(f"Saved {len(rows)} row(s) to {output_file.name}")


if __name__ == "__main__":
    main()

