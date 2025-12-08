#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2025 DraVee
# SPDX-License-Identifier: GPL-3.0-or-later

import sys
import pandas as pd
import matplotlib.pyplot as plt
import glob
import os
import colorsys

# Check required Python modules
required_modules = ["pandas", "matplotlib"]
missing_modules = []

for mod in required_modules:
    try:
        __import__(mod)
    except ImportError:
        missing_modules.append(mod)

if missing_modules:
    print(f"Error: Missing required Python modules: {', '.join(missing_modules)}")
    print("Please install them, e.g.:")
    print(f"    python3 -m pip install {' '.join(missing_modules)}")
    sys.exit(1)

# Get log folder from command-line argument
if len(sys.argv) < 2:
    print("Usage: python3 compare_logs.py <log_folder>")
    sys.exit(1)

log_base_folder = os.path.expanduser(sys.argv[1])
if not os.path.isdir(log_base_folder):
    print(f"Error: '{log_base_folder}' is not a valid folder")
    sys.exit(1)

# Find all CSV files recursively (ignore summary CSVs)
csv_files = sorted(glob.glob(os.path.join(log_base_folder, "**/eden_*.csv"), recursive=True))
csv_files = [f for f in csv_files if not f.endswith("_summary.csv")]

if not csv_files:
    print(f"No CSV files found in {log_base_folder} or its subfolders")
    sys.exit(0)

# Prepare plotting
plt.figure(figsize=(14, 7))

# Gather build folders
build_folders = sorted({os.path.basename(os.path.dirname(os.path.dirname(f))) for f in csv_files})
n_builds = len(build_folders)

# Generate base colors for each build folder (HSV evenly spaced)
build_colors = {}
for i, build in enumerate(build_folders):
    h = i / n_builds  # hue evenly spaced
    s = 0.7
    v = 0.9
    rgb = colorsys.hsv_to_rgb(h, s, v)
    build_colors[build] = rgb

# Track how many CSVs plotted per build to adjust brightness
build_counts = {b: 0 for b in build_folders}

stats = []

for csv_file in csv_files:
    # Relative path from base folder
    relative_path = os.path.relpath(csv_file, log_base_folder)

    # Read eden-cli version if exists
    log_dir = os.path.dirname(csv_file)
    version_file = os.path.join(log_dir, "eden-cli-version.txt")
    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            eden_version = f.read().strip()
    else:
        eden_version = "unknown version"

    # Corresponding summary file
    summary_file = csv_file.replace(".csv", "_summary.csv")
    
    # Skip empty CSVs
    if os.path.getsize(csv_file) == 0:
        print(f"Skipping {relative_path}: file is empty")
        continue

    # Read main CSV (skip system info lines)
    df = pd.read_csv(csv_file, skiprows=2)
    df.columns = df.columns.str.strip()
    
    if 'fps' not in df.columns:
        print(f"Skipping {relative_path}: no 'fps' column found")
        continue

    y = df['fps']

    # --- FILTRAR OUTLIERS ---
    mean_y = y.mean()
    std_y = y.std()
    y_filtered = y[(y >= mean_y - 3*std_y) & (y <= mean_y + 3*std_y)]
    x_filtered = range(len(y_filtered))
    # ------------------------

    # Compute statistics from filtered data
    mean_fps = y_filtered.mean()
    min_fps = y_filtered.min()
    max_fps = y_filtered.max()

    # Read summary CSV if exists
    summary_text = ""
    if os.path.exists(summary_file):
        try:
            df_sum = pd.read_csv(summary_file)
            avg = float(df_sum['Average FPS'][0])
            p0_1 = float(df_sum['0.1% Min FPS'][0])
            p1 = float(df_sum['1% Min FPS'][0])
            p97 = float(df_sum['97% Percentile FPS'][0])
            summary_text = f" | summary avg={avg:.1f}, 0.1%={p0_1:.1f}, 1%={p1:.1f}, 97%={p97:.1f}"
        except Exception as e:
            print(f"Could not read summary for {summary_file}: {e}")

    # Store stats including version
    stats.append((relative_path, mean_fps, min_fps, max_fps, summary_text, eden_version))

    # Determine build folder and assign color with slight variation
    build_folder = os.path.basename(os.path.dirname(os.path.dirname(csv_file)))
    base_rgb = build_colors[build_folder]
    count = build_counts[build_folder]
    # Slightly vary brightness (value) for multiple runs in same build
    factor = 0.9 - 0.15 * count
    rgb = tuple(min(max(c * factor, 0), 1) for c in base_rgb)
    build_counts[build_folder] += 1

    # Plot FPS line with filtered data
    plt.plot(
        x_filtered, y_filtered,
        label=f"{relative_path} (avg={mean_fps:.1f}) [{eden_version}]{summary_text}",
        color=rgb
    )

# Configure plot
plt.xlabel('Frame')
plt.ylabel('FPS')
plt.title('FPS Comparison Across All Builds (Outliers Removed)')
plt.legend()
plt.grid(True)
plt.tight_layout()

# Save plot
png_file = os.path.join(os.getcwd(), "fps_comparison_all_builds.png")
plt.savefig(png_file, dpi=200)
plt.show()

# Print concise statistics grouped by build folder
print("\nFPS Summary by build folder (concise):")
for name, mean_fps, min_fps, max_fps, summary_text, eden_version in stats:
    log_folder = os.path.dirname(name)
    build_folder = os.path.basename(os.path.dirname(log_folder))
    version_short = eden_version.split()[0] if eden_version != "unknown version" else "unknown"
    print(f"{build_folder} | {version_short} | mean={mean_fps:.1f}, min={min_fps:.1f}, max={max_fps:.1f}")

print("\n----------------------------")
print(f"Total CSV files processed: {len(stats)}")

# Track build folders (without timestamps)
build_folders_paths = set()
for csv_file in csv_files:
    run_folder = os.path.dirname(csv_file)
    build_folder = os.path.dirname(run_folder)
    build_folders_paths.add(build_folder)

print("\nBuild folders containing CSVs:")
for folder in sorted(build_folders_paths):
    print(f" - {folder}")

print(f"Graph saved as: {png_file}")

