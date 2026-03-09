#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SH="$SCRIPT_DIR/run.sh"
VENV="$SCRIPT_DIR/venv"
CRON_ENTRY="0 * * * * $RUN_SH"

echo "=== Macabi Appointment Checker Setup ==="
echo "Script directory: $SCRIPT_DIR"

# Create virtual environment
if [ ! -d "$VENV" ]; then
    echo "[1/4] Creating virtual environment..."
    python3 -m venv "$VENV"
else
    echo "[1/4] Virtual environment already exists, skipping."
fi

# Install dependencies
echo "[2/4] Installing dependencies..."
source "$VENV/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"

# Install Chromium for Playwright
echo "[3/4] Installing Playwright Chromium browser..."
playwright install chromium

# Create logs directory
mkdir -p "$SCRIPT_DIR/logs"

# Make scripts executable
chmod +x "$RUN_SH"

# Install cron entry (idempotent)
echo "[4/4] Installing cron entry..."
EXISTING_CRON="$(crontab -l 2>/dev/null || true)"

if echo "$EXISTING_CRON" | grep -qF "$RUN_SH"; then
    echo "Cron entry already present, skipping."
else
    (echo "$EXISTING_CRON"; echo "$CRON_ENTRY") | crontab -
    echo "Cron entry added: $CRON_ENTRY"
fi

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. cp .env.example .env"
echo "  2. Edit .env with your credentials"
echo "  3. For visual debugging: set HEADLESS=false in .env"
echo "  4. Test manually: source venv/bin/activate && python checker.py"
echo "  5. Check logs: tail -f logs/checker.log"
echo "  6. Verify cron: crontab -l"
