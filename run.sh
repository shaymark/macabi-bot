#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/venv/bin/activate"

shopt -s nullglob
job_files=("$SCRIPT_DIR/jobs/"*.env)
shopt -u nullglob

if [ ${#job_files[@]} -gt 0 ]; then
    for job_file in "${job_files[@]}"; do
        echo "--- Running job: $job_file ---" >> "$SCRIPT_DIR/logs/checker.log" 2>&1
        python "$SCRIPT_DIR/checker.py" --job "$job_file" >> "$SCRIPT_DIR/logs/checker.log" 2>&1
    done
else
    # Backward-compatible fallback: no jobs/ files, use root .env
    python "$SCRIPT_DIR/checker.py" >> "$SCRIPT_DIR/logs/checker.log" 2>&1
fi
