#!/bin/bash

if [ -f .server.pid ]; then
    PID=$(cat .server.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "Stopping server (PID: $PID)..."
        kill $PID
        sleep 2
        if ps -p $PID > /dev/null 2>&1; then
            echo "Force killing..."
            kill -9 $PID
        fi
        rm .server.pid
        echo "✓ Server stopped"
    else
        echo "Server is not running (stale PID file)"
        rm .server.pid
    fi
else
    echo "No PID file found. Checking for running processes..."
    pkill -f "python main.py api" && echo "✓ Killed running server" || echo "No server process found"
fi
