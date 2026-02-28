#!/bin/bash
# Test connection to remote OCR server

if [ -z "$1" ]; then
    echo "Usage: ./test_connection.sh SERVER_IP"
    echo "Example: ./test_connection.sh 192.168.1.100"
    exit 1
fi

SERVER_IP=$1
PORT=${2:-8000}

echo "=========================================="
echo "Testing OCR Server Connection"
echo "=========================================="
echo "Server: http://$SERVER_IP:$PORT"
echo ""

# Test health endpoint
echo "1. Testing health endpoint..."
HEALTH=$(curl -s -w "\n%{http_code}" http://$SERVER_IP:$PORT/health 2>/dev/null)
HTTP_CODE=$(echo "$HEALTH" | tail -n1)
RESPONSE=$(echo "$HEALTH" | head -n1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✓ Health check passed: $RESPONSE"
else
    echo "   ✗ Health check failed (HTTP $HTTP_CODE)"
    echo "   Make sure server is running and port $PORT is open"
    exit 1
fi

# Test docs endpoint
echo ""
echo "2. Testing Swagger UI..."
DOCS=$(curl -s -o /dev/null -w "%{http_code}" http://$SERVER_IP:$PORT/docs 2>/dev/null)
if [ "$DOCS" = "200" ]; then
    echo "   ✓ Swagger UI accessible at: http://$SERVER_IP:$PORT/docs"
else
    echo "   ✗ Swagger UI not accessible"
fi

echo ""
echo "=========================================="
echo "✓ Connection Test Complete!"
echo "=========================================="
echo ""
echo "Your Java app configuration:"
echo "export PYTHON_SERVICE_BASE_URL=http://$SERVER_IP:$PORT"
echo ""
