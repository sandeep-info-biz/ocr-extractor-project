#!/bin/bash

echo "Restarting OCR Remote Server..."
./stop_server.sh
sleep 2
./start_server.sh
