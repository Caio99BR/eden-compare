#!/bin/bash -e

# SPDX-FileCopyrightText: Copyright 2025 DraVee
# SPDX-License-Identifier: GPL-3.0-or-later

# Usage/help
show_help() {
    echo "Usage: $0 [--temp | <log_folder>]"
    echo
    echo "Options:"
    echo "  --temp       Use a temporary folder (mktemp) for logs"
    echo "  <log_folder> Use the specified folder for logs"
    echo "  -h, --help   Show this help message"
}

# Parse arguments
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    show_help
    exit 0
fi

if [[ "$1" == "--temp" ]]; then
    BASE_LOG_DIR=$(mktemp -d)
    echo "Using temporary log folder: $BASE_LOG_DIR"
elif [[ -n "$1" ]]; then
    BASE_LOG_DIR="$1"
else
    BASE_LOG_DIR=".compare/logs"
fi

mkdir -p "$BASE_LOG_DIR"

# Check required programs
for cmd in python3 mangohud find; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: $cmd is not installed. Please install it before running this script."
        exit 1
    fi
done

# Log duration
WAIT_DURATION=5
LOG_DURATION=$((60 + WAIT_DURATION))

# Loop through all build*/bin/eden executables
for eden_bin in build*/Eden*.AppImage; do
    if [[ ! -x "$eden_bin" ]]; then
        echo "Skipping $eden_bin: not executable"
        continue
    fi

    # Extract build path and make a unique folder name
    build_path=$(dirname "$eden_bin")
    build_name=$(echo "$build_path" | tr '/' '_')

    # Timestamp for unique log folder
    timestamp=$(date +%Y-%m-%d_%H-%M-%S)
    log_dir="$BASE_LOG_DIR/$build_name/$timestamp"
    mkdir -p "$log_dir"

    # Save eden-cli version for this build
    eden_cli="$build_path/eden-cli"
    if [[ -x "$eden_cli" ]]; then
        "$eden_cli" --version > "$log_dir/eden-cli-version.txt" 2>&1
    else
        echo "$build_name" > "$log_dir/eden-cli-version.txt"
    fi

    echo "Running $eden_bin, logs will be saved in $log_dir"

    # Set MangoHud environment variables
    export MANGOHUD=1
    export MANGOHUD_LOG=1
    export MANGOHUD_CONFIG="output_folder=$log_dir;log_duration=$LOG_DURATION;autostart_log=$WAIT_DURATION"

    # Run Eden in background and capture its PID
    QT_QPA_PLATFORM=xcb "$eden_bin" &
    EDEN_PID=$!

    summary_file=""
    while true; do
        # Check if the process is still running
        if ! kill -0 "$EDEN_PID" 2>/dev/null; then
            echo "$eden_bin on $EDEN_PID died before generating log, skipping..."
            break
        fi

        # Monitor MangoHud logs in real time for _summary.csv creation
        summary_file=$(find "$log_dir" -name "*_summary.csv" | head -n 1)
        if [[ -n "$summary_file" && -f "$summary_file" ]]; then
            echo "Summary detected: $summary_file"

            # Kill the Eden process
            echo "Stopping $eden_bin..."
            kill "$EDEN_PID"
            sleep 1
            kill -9 "$EDEN_PID" 2>/dev/null || true
            wait "$EDEN_PID" 2>/dev/null || true
            break
        fi

        sleep 1
    done
done

# Run comparison script
echo "All builds finished. Running compare_logs.py..."
python3 tools/test/compare_logs.py "$BASE_LOG_DIR"

