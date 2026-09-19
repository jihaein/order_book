"""Canonical application entrypoint.

Run ``python src/app.py`` from the project root, or import ``app`` with an
ASGI server. Both routes serve the same FastAPI backend and browser UI.
"""

import uvicorn

from server import app


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
