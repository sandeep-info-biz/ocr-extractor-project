#!/bin/bash
set -e

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Default values
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}

echo "Starting OCR Remote Server..."
echo "Host: $HOST"
echo "Port: $PORT"

# Activate virtual environment
source .venv/bin/activate

# Create logs directory
mkdir -p logs

# Start server in background
nohup python main.py api --host $HOST --port $PORT > logs/server.log 2>&1 &
SERVER_PID=$!

# Save PID
echo $SERVER_PID > .server.pid

echo "✓ Server started with PID: $SERVER_PID"
echo ""
echo "Server is running at: http://$HOST:$PORT"
echo "Swagger UI: http://$HOST:$PORT/docs"
echo "Health check: http://$HOST:$PORT/health"
echo ""
echo "View logs: tail -f logs/server.log"
echo "Stop server: ./stop_server.sh"
