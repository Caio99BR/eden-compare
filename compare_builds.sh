#!/bin/bash -e

# SPDX-FileCopyrightText: Copyright 2025 DraVee
# SPDX-License-Identifier: GPL-3.0-or-later

# Usage/help
show_help() {
    echo "[compare_build.sh] Usage: $0"
    echo
    echo "[compare_build.sh] Options:"
    echo "  -h, --help    Show this help message"
}

# Parse arguments
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    show_help
    exit 0
fi

# Default directories
DEFAULT_BUILD_DIR="${DEFAULT_BUILD_DIR:-./build}"
DEFAULT_EXECUTABLES_DIR="${DEFAULT_EXECUTABLES_DIR:-./artifacts}"
BASE_LOG_DIR="${BASE_LOG_DIR:-./.cache/compare/logs}"
TEMP_LOG_DIR=$(mktemp -d -t eden-logs-XXXXXX)

# Cleanup old logs, preserving '_master' logs, unless forced
if [[ -d "$BASE_LOG_DIR" ]] && [[ $(find "$BASE_LOG_DIR" -mindepth 1 -print -quit) ]]; then
    echo -n "[compare_build.sh] Clean old logs in '$BASE_LOG_DIR' (except *_master)? (y/n/f): "
    read -n1 answer
    echo
    answer=$(echo "$answer" | tr '[:upper:]' '[:lower:]')
    if [[ "$answer" == "y" ]]; then
        echo "[compare_build.sh] Cleaning old logs (keeping *_master logs)..."
        for item in "$BASE_LOG_DIR"/*/*; do
            base=$(basename "$item")
            if [[ "$base" != *_master ]]; then
                rm -rf "$item"
            fi
        done
    elif [[ "$answer" == "f" ]]; then
        echo "[compare_build.sh] Force cleaning all logs (including *_master)..."
        rm -rf "$BASE_LOG_DIR"/*
    else
        echo "[compare_build.sh] Keeping existing logs!"
    fi
fi

mkdir -p "$BASE_LOG_DIR"

# Check required programs
for cmd in python3 mangohud find; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "[compare_build.sh] Error: $cmd is not installed. Please install it before running this script."
        exit 1
    fi
done

# Log duration
WAIT_DURATION=5
LOG_DURATION=$((${PLAYTIME:-60} + WAIT_DURATION))

# Detect all Eden executables
EXECUTABLES=()
echo "[compare_build.sh] Searching for executables..."

search_execs() {
    local dir="$1"
    [[ -d "$dir" ]] || return 0

    while IFS= read -r -d '' file; do
        EXECUTABLES+=("$file")
    done < <(
        find "$dir"/ -maxdepth 1 -type f \
            \( -name "*.exe" -o -name "*.AppImage" -o -name "eden*" -o -name "Eden*" \) \
            -print0 2>/dev/null
    )
}

# Search default build/bin and artifacts
shopt -s nullglob
for d in "$DEFAULT_BUILD_DIR"*/bin; do
    search_execs "$d"
done
shopt -u nullglob
search_execs "$DEFAULT_EXECUTABLES_DIR"

# Add master executables (kept separately)
MASTER_EXECUTABLES=()
if [[ -d "$DEFAULT_EXECUTABLES_DIR/master" ]]; then
    while IFS= read -r -d '' master_bin; do
        MASTER_EXECUTABLES+=("$master_bin")
    done < <(
        find "$DEFAULT_EXECUTABLES_DIR/master" -maxdepth 1 -type f \
            \( -name "*.exe" -o -name "*.AppImage" -o -name "eden*" -o -name "Eden*" \) -print0
    )
fi

# Combine all executables (normal + master)
ALL_EXECUTABLES=("${EXECUTABLES[@]}" "${MASTER_EXECUTABLES[@]}")

if [[ ${#ALL_EXECUTABLES[@]} -eq 0 ]]; then
    echo "[compare_build.sh] ERROR: No Eden executables found!"
    echo "[compare_build.sh] Searched in: $DEFAULT_EXECUTABLES_DIR/, $DEFAULT_BUILD_DIR*/bin/"
    exit 1
fi

echo "[compare_build.sh] Found ${#ALL_EXECUTABLES[@]} executables."
printf '  - %s\n' "${ALL_EXECUTABLES[@]}"

# Run all executables
for eden_bin in "${ALL_EXECUTABLES[@]}"; do
    if [[ ! -x "$eden_bin" ]]; then
        echo "[compare_build.sh] $eden_bin is not executable, attempting chmod +x..."
        chmod +x "$eden_bin"
        if [[ ! -x "$eden_bin" ]]; then
            echo "[compare_build.sh] Skipping $eden_bin: still not executable after chmod"
            continue
        fi
    fi

    # Clean shaders cache
    rm -rf "$HOME/.local/share/eden/shader/"

    # Extract build name
    base=$(basename "$eden_bin")
    base_no_ext="${base%.*}"
    parent_dir=$(dirname "$eden_bin")

    if [[ "$base_no_ext" == "eden" || "$base_no_ext" == "Eden" ]]; then
        build_name=$(echo "$parent_dir" | tr '/' '_')
    else
        build_name="$base_no_ext"
    fi

    # If executable is in master folder, append "_master" to build_name
    if [[ "$eden_bin" == *"/master/"* ]]; then
        build_name="${build_name}_master"
    fi

    # Timestamp for unique log folder
    timestamp=$(date +%y%m%d_%H%M)
    temp_log_dir="$TEMP_LOG_DIR/$build_name/$timestamp"
    mkdir -p "$temp_log_dir"

    # Save eden-cli version
    eden_cli="$(dirname "$eden_bin")/eden-cli"
    if [[ -x "$eden_cli" ]]; then
        "$eden_cli" --version > "$temp_log_dir/eden-cli-version.txt" 2>&1
    else
        echo "$build_name" > "$temp_log_dir/eden-cli-version.txt"
    fi

    echo "[compare_build.sh] Running $eden_bin"
    echo "[compare_build.sh] Logs will be temporarily saved in $temp_log_dir"

    # Run Eden with MangoHud
    MANGOHUD=1 \
        MANGOHUD_LOG=1 \
        MANGOHUD_CONFIG="output_folder=$temp_log_dir;log_duration=$LOG_DURATION;autostart_log=$WAIT_DURATION" \
        QT_QPA_PLATFORM=xcb \
        "$eden_bin" &
    EDEN_PID=$!
    sleep $LOG_DURATION

    summary_file=""
    while true; do
        if ! kill -0 "$EDEN_PID" 2>/dev/null; then
            echo "[compare_build.sh] $eden_bin (PID $EDEN_PID) died before generating log, skipping..."
            break
        fi

        summary_file=$(find "$temp_log_dir" -name "*_summary.csv" | head -n 1)
        if [[ -f "$summary_file" ]]; then
            echo "[compare_build.sh] Summary detected: $summary_file"

            # Kill process
            echo "[compare_build.sh] Force stopping $eden_bin..."
            pgrep -P "$EDEN_PID" | xargs -r kill -9 2>/dev/null
            kill -9 "$EDEN_PID" 2>/dev/null
            while kill -0 "$EDEN_PID" 2>/dev/null || pgrep -P "$EDEN_PID" >/dev/null 2>&1; do
                sleep 0.5
            done

            # Capture game_name and game_id
            eden_log="$HOME/.local/share/eden/log/eden_log.txt"
            if [[ -f "$eden_log" ]]; then
                last_loading_line=$(grep "Loading " "$eden_log" | tail -n 1)
                if [[ -n "$last_loading_line" ]]; then
                    game_name=$(echo "$last_loading_line" | sed -n 's/.*Loading \(.*\) (.*/\1/p')
                    game_id=$(echo "$last_loading_line" | grep -oP '\([0-9A-Fa-f]{16}\)' | tr -d '()')

                    log_dir="$BASE_LOG_DIR/$game_id/$build_name/$timestamp"
                    mkdir -p "$log_dir"

                    # Move logs
                    mv "$temp_log_dir"/* "$log_dir"/

                    # Save game info
                    echo "$game_name" > "$log_dir/eden-cli-game-name.txt"
                    echo "$game_id" > "$log_dir/eden-cli-game-id.txt"

                    echo "[compare_build.sh] Detected game: $game_name ($game_id)"
                else
                    echo "[compare_build.sh] No 'Loading' entry found in eden_log.txt"
                fi
            else
                echo "[compare_build.sh] Eden log not found at $eden_log"
            fi
            break
        fi

        sleep $WAIT_DURATION
    done
done

# Cleanup tmp files
rm -rf "$TEMP_LOG_DIR/"*

# Run comparison script
echo "[compare_build.sh] All builds finished. Running compare_logs.py..."
python3 ./tools/test/compare_logs.py "$BASE_LOG_DIR" --filter-percent

