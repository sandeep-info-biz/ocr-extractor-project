#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
RUN_DIR="$ROOT_DIR/.run"
PID_FILE="$RUN_DIR/service.pids"
mkdir -p "$RUN_DIR"

source "$ROOT_DIR/scripts/bootstrap_dev_env.sh" --quiet

PY_HOST="${PY_HOST:-127.0.0.1}"
PY_PORT="${PY_PORT:-8000}"
START_WORKER="${START_WORKER:-1}"
WORKER_POLL_SECONDS="${WORKER_POLL_SECONDS:-0.8}"
WORKER_MAX_ATTEMPTS="${WORKER_MAX_ATTEMPTS:-3}"
JAVA_CMD="${JAVA_CMD:-mvn spring-boot:run}"
LAUNCH_MODE="${LAUNCH_MODE:-inline}" # inline | separate

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
echo "Launch mode: $LAUNCH_MODE"
echo

pids=()

escape_for_applescript() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

launch_in_terminal_window() {
  local title="$1"
  local command="$2"
  local esc
  esc="$(escape_for_applescript "cd \"$ROOT_DIR\"; source \"$ROOT_DIR/scripts/bootstrap_dev_env.sh\" --quiet; echo \"[$title]\"; $command")"
  osascript -e "tell application \"Terminal\" to activate" \
            -e "tell application \"Terminal\" to do script \"$esc\"" >/dev/null
}

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

if [[ "$LAUNCH_MODE" == "separate" ]]; then
  if [[ "$OSTYPE" != darwin* ]]; then
    echo "LAUNCH_MODE=separate is only supported on macOS Terminal."
    echo "Use inline mode or VS Code task: Start Full Stack (3 terminals)."
    exit 1
  fi

  echo "[1/3] Opening Python API in a new Terminal window..."
  launch_in_terminal_window "Python API" "\"$PYTHON_BIN\" main.py api --host \"$PY_HOST\" --port \"$PY_PORT\""

  if [[ "$START_WORKER" == "1" ]]; then
    echo "[2/3] Opening Python worker in a new Terminal window..."
    launch_in_terminal_window "Python Worker" "\"$PYTHON_BIN\" main.py worker --poll-seconds \"$WORKER_POLL_SECONDS\" --max-attempts \"$WORKER_MAX_ATTEMPTS\""
  else
    echo "[2/3] Skipping Python worker (START_WORKER=$START_WORKER)"
  fi

  echo "[3/3] Opening Java Spring Boot in a new Terminal window..."
  launch_in_terminal_window "Java Spring" "bash -lc \"$JAVA_CMD\""
  echo "Launched in separate Terminal windows."
  echo "For VS Code integrated terminals, use: Run Task -> Start Full Stack (3 terminals)"
  trap - EXIT INT TERM
  exit 0
fi

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
