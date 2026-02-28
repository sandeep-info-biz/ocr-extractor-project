#!/bin/bash
# Verify remote_server folder is ready for deployment

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Verifying Remote Server Package                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

ERRORS=0

# Check required files
echo "Checking required files..."
FILES=(
    "main.py"
    "requirements.txt"
    "setup.sh"
    "start_server.sh"
    "stop_server.sh"
    "restart_server.sh"
    "status.sh"
    ".env.example"
    "README.md"
    "QUICKSTART.md"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        echo "  ✗ $file (MISSING)"
        ERRORS=$((ERRORS + 1))
    fi
done

# Check required directories
echo ""
echo "Checking required directories..."
DIRS=(
    "app"
    "data"
    "models"
    "logs"
)

for dir in "${DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "  ✓ $dir/"
    else
        echo "  ✗ $dir/ (MISSING)"
        ERRORS=$((ERRORS + 1))
    fi
done

# Check app files
echo ""
echo "Checking app files..."
APP_FILES=(
    "app/__init__.py"
    "app/api.py"
    "app/ocr.py"
    "app/parser.py"
)

for file in "${APP_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        echo "  ✗ $file (MISSING)"
        ERRORS=$((ERRORS + 1))
    fi
done

# Check script permissions
echo ""
echo "Checking script permissions..."
SCRIPTS=(
    "setup.sh"
    "start_server.sh"
    "stop_server.sh"
    "restart_server.sh"
    "status.sh"
    "test_connection.sh"
    "deploy_to_remote.sh"
)

for script in "${SCRIPTS[@]}"; do
    if [ -x "$script" ]; then
        echo "  ✓ $script (executable)"
    else
        echo "  ⚠ $script (not executable - will fix on server)"
    fi
done

# Calculate package size
echo ""
echo "Package information..."
SIZE=$(du -sh . | cut -f1)
echo "  Total size: $SIZE"

FILE_COUNT=$(find . -type f | wc -l)
echo "  Total files: $FILE_COUNT"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $ERRORS -eq 0 ]; then
    echo "✅ VERIFICATION PASSED!"
    echo ""
    echo "Package is ready for deployment."
    echo ""
    echo "Next steps:"
    echo "  1. Deploy: ./deploy_to_remote.sh user@server-ip"
    echo "  2. Or manually copy this folder to your server"
    echo ""
else
    echo "❌ VERIFICATION FAILED!"
    echo ""
    echo "Found $ERRORS missing files/directories."
    echo "Please check the errors above."
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
