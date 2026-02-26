#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
RUN_DIR="$ROOT_DIR/.run"
PID_FILE="$RUN_DIR/service.pids"
mkdir -p "$RUN_DIR"

PY_HOST="${PY_HOST:-127.0.0.1}"
PY_PORT="${PY_PORT:-8000}"
START_WORKER="${START_WORKER:-1}"
WORKER_POLL_SECONDS="${WORKER_POLL_SECONDS:-0.8}"
WORKER_MAX_ATTEMPTS="${WORKER_MAX_ATTEMPTS:-3}"
JAVA_CMD="${JAVA_CMD:-mvn spring-boot:run}"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

echo "Project root: $ROOT_DIR"
echo "Python: $PYTHON_BIN"
echo "Python API: http://$PY_HOST:$PY_PORT"
echo "Start worker: $START_WORKER"
echo "Java command: $JAVA_CMD"
echo

pids=()

save_pids() {
  {
    for pid in "${pids[@]:-}"; do
      echo "$pid"
    done
  } >"$PID_FILE"
}

cleanup() {
  echo
  echo "Stopping services..."
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  wait || true
  rm -f "$PID_FILE"
  echo "Stopped."
}

trap cleanup EXIT INT TERM

echo "[1/3] Starting Python API..."
"$PYTHON_BIN" main.py api --host "$PY_HOST" --port "$PY_PORT" &
pids+=("$!")
save_pids

if [[ "$START_WORKER" == "1" ]]; then
  echo "[2/3] Starting Python worker..."
  "$PYTHON_BIN" main.py worker --poll-seconds "$WORKER_POLL_SECONDS" --max-attempts "$WORKER_MAX_ATTEMPTS" &
  pids+=("$!")
  save_pids
else
  echo "[2/3] Skipping Python worker (START_WORKER=$START_WORKER)"
fi

echo "[3/3] Starting Java Spring Boot app..."
echo "UI will be available at: http://127.0.0.1:8080"
bash -lc "$JAVA_CMD" &
pids+=("$!")
save_pids

echo
echo "All services started. Press Ctrl+C to stop everything."
wait
