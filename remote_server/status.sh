#!/bin/bash

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}

echo "=========================================="
echo "OCR Remote Server Status"
echo "=========================================="

if [ -f .server.pid ]; then
    PID=$(cat .server.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "Status: ✓ RUNNING"
        echo "PID: $PID"
        echo "Uptime: $(ps -o etime= -p $PID)"
        echo ""
        echo "Endpoints:"
        echo "  - Health: http://$HOST:$PORT/health"
        echo "  - Swagger: http://$HOST:$PORT/docs"
        echo "  - OpenAPI: http://$HOST:$PORT/openapi.json"
        echo ""
        echo "Recent logs:"
        tail -n 10 logs/server.log
    else
        echo "Status: ✗ NOT RUNNING (stale PID)"
    fi
else
    echo "Status: ✗ NOT RUNNING"
    echo ""
    echo "Start server: ./start_server.sh"
fi
