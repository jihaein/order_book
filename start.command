#!/bin/zsh
cd "${0:A:h}"
if ! curl -fsS http://127.0.0.1:8000/api/snapshot >/dev/null 2>&1; then
  mkdir -p logs
  nohup .venv/bin/python src/app.py >>logs/app.log 2>&1 &
  for attempt in {1..30}; do
    curl -fsS http://127.0.0.1:8000/api/snapshot >/dev/null 2>&1 && break
    sleep 0.2
  done
fi
open http://127.0.0.1:8000
