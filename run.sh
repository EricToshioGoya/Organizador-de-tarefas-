#!/usr/bin/env sh
# Organizador de Tarefas em servidor Linux/macOS: prepara o ambiente e inicia o servidor.
#   ./run.sh            → porta 8000 em todas as interfaces
#   PORT=8080 ./run.sh
#   ./run.sh test       → testes com cobertura
set -eu
cd "$(dirname "$0")"
VENV="${VENV:-.venv}"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check -q -r requirements-dev.txt
if [ "${1:-}" = "test" ]; then
  SCHEDULER_ENABLED=false exec "$VENV/bin/python" -m pytest --cov=app --cov-report=term-missing
fi
exec "$VENV/bin/python" -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --proxy-headers
