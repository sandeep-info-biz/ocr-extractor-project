#!/bin/bash
# One-command deployment to remote server
# Usage: ./deploy_to_remote.sh user@server-ip

set -e

if [ -z "$1" ]; then
    echo "Usage: ./deploy_to_remote.sh user@server-ip"
    echo "Example: ./deploy_to_remote.sh ubuntu@192.168.1.100"
    exit 1
fi

REMOTE=$1
REMOTE_DIR="/home/$(echo $REMOTE | cut -d'@' -f1)/ocr-remote-server"

echo "=========================================="
echo "Deploying OCR Server to Remote Machine"
echo "=========================================="
echo "Target: $REMOTE"
echo "Remote directory: $REMOTE_DIR"
echo ""

# Create remote directory
echo "Creating remote directory..."
ssh $REMOTE "mkdir -p $REMOTE_DIR"

# Copy files
echo "Copying files..."
rsync -avz --progress \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.server.pid' \
    --exclude='logs/*' \
    remote_server/ $REMOTE:$REMOTE_DIR/

echo ""
echo "✓ Files copied successfully!"
echo ""
echo "=========================================="
echo "Next Steps (run on remote server):"
echo "=========================================="
echo ""
echo "1. SSH into server:"
echo "   ssh $REMOTE"
echo ""
echo "2. Go to directory:"
echo "   cd $REMOTE_DIR"
echo ""
echo "3. Run setup:"
echo "   chmod +x *.sh"
echo "   ./setup.sh"
echo ""
echo "4. Start server:"
echo "   ./start_server.sh"
echo ""
echo "5. Update your local Java app:"
echo "   export PYTHON_SERVICE_BASE_URL=http://$(echo $REMOTE | cut -d'@' -f2):8000"
echo ""
