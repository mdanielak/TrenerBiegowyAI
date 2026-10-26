#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ ! -x .venv/bin/python ]]; then
    echo "Brak .venv/bin/python. Przygotuj srodowisko zgodnie z README.md." >&2
    exit 1
fi

echo "Dashboard: http://127.0.0.1:8001"
echo "Zatrzymanie: Ctrl+C"
exec .venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8001
