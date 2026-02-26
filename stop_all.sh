#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

RUN_DIR="$ROOT_DIR/.run"
PID_FILE="$RUN_DIR/service.pids"

kill_pid_if_alive() {
  local pid="$1"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    return 0
  fi
  return 1
}

echo "Stopping OCR Extractor stack..."

if [[ -f "$PID_FILE" ]]; then
  echo "Using PID file: $PID_FILE"
  pids=()
  while IFS= read -r line; do
    [[ -n "${line:-}" ]] || continue
    pids+=("$line")
  done <"$PID_FILE"
  for pid in "${pids[@]:-}"; do
    [[ -n "${pid:-}" ]] || continue
    kill_pid_if_alive "$pid" || true
  done

  # Give processes a moment to exit cleanly.
  sleep 2

  for pid in "${pids[@]:-}"; do
    [[ -n "${pid:-}" ]] || continue
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  done

  rm -f "$PID_FILE"
fi

# Fallback cleanup for manually started/leftover processes.
pkill -f "main.py api" >/dev/null 2>&1 || true
pkill -f "main.py worker" >/dev/null 2>&1 || true
pkill -f "spring-boot:run" >/dev/null 2>&1 || true
pkill -f "com.ocr.extractor.OcrExtractorApplication" >/dev/null 2>&1 || true

echo "Stopped."
