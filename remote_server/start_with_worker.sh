#!/bin/bash
set -e

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Default values
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}
WORKER_POLL_SECONDS=${WORKER_POLL_SECONDS:-0.8}
WORKER_MAX_ATTEMPTS=${WORKER_MAX_ATTEMPTS:-3}

echo "Starting OCR Remote Server with Worker..."
echo "Host: $HOST"
echo "Port: $PORT"
echo "Worker poll: ${WORKER_POLL_SECONDS}s"

# Activate virtual environment
source .venv/bin/activate

# Create logs directory
mkdir -p logs

# Start API server in background
echo "Starting Python API..."
nohup python main.py api --host $HOST --port $PORT > logs/api.log 2>&1 &
API_PID=$!
echo $API_PID > .api.pid
echo "✓ API started with PID: $API_PID"

# Start worker in background
echo "Starting Python Worker..."
nohup python main.py worker --poll-seconds $WORKER_POLL_SECONDS --max-attempts $WORKER_MAX_ATTEMPTS > logs/worker.log 2>&1 &
WORKER_PID=$!
echo $WORKER_PID > .worker.pid
echo "✓ Worker started with PID: $WORKER_PID"

# Save both PIDs
echo "$API_PID" > .server.pid
echo "$WORKER_PID" >> .server.pid

echo ""
echo "✓ Both services started!"
echo ""
echo "API Server: http://$HOST:$PORT"
echo "Swagger UI: http://$HOST:$PORT/docs"
echo "Health check: http://$HOST:$PORT/health"
echo ""
echo "View API logs: tail -f logs/api.log"
echo "View Worker logs: tail -f logs/worker.log"
echo "Stop services: ./stop_server.sh"
