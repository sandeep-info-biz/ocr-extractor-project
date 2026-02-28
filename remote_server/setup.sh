#!/bin/bash
set -e

echo "=========================================="
echo "OCR Remote Server Setup"
echo "=========================================="

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed!"
    echo "Install Python 3.11 or higher first."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✓ Found Python $PYTHON_VERSION"

# Install system dependencies
echo ""
echo "Installing system dependencies..."
if command -v apt-get &> /dev/null; then
    # Ubuntu/Debian
    sudo apt-get update -y
    sudo apt-get install -y tesseract-ocr poppler-utils
elif command -v yum &> /dev/null; then
    # CentOS/RHEL
    sudo yum install -y tesseract poppler-utils
elif command -v brew &> /dev/null; then
    # macOS
    brew install tesseract poppler
else
    echo "WARNING: Could not detect package manager. Install tesseract-ocr and poppler manually."
fi

# Create virtual environment
echo ""
echo "Creating Python virtual environment..."
python3 -m venv .venv

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install Python dependencies
echo ""
echo "Installing Python packages (this may take a few minutes)..."
pip install --upgrade pip
pip install -r requirements.txt

# Download spaCy model
echo ""
echo "Downloading spaCy English model..."
python -m spacy download en_core_web_sm

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p data/uploads
mkdir -p models
mkdir -p logs

# Copy default config if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✓ Created .env file (edit this to customize settings)"
fi

echo ""
echo "=========================================="
echo "✓ Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file if needed: nano .env"
echo "2. Start server: ./start_server.sh"
echo "3. Check status: ./status.sh"
echo ""
