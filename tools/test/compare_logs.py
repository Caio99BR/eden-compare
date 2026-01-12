#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2025 DraVee
# SPDX-License-Identifier: GPL-3.0-or-later

import sys
import glob
import os
import colorsys

required_modules = ["pandas", "matplotlib"]
missing_modules = [m for m in required_modules if __import__("importlib.util").util.find_spec(m) is None]
if missing_modules:
    print(f"[compare_logs.py] Error: Missing required Python modules: {', '.join(missing_modules)}")
    print(f"[compare_logs.py] Please install with: python3 -m pip install {' '.join(missing_modules)}")
    sys.exit(1)

import pandas as pd
import matplotlib.pyplot as plt

FILTER_PERCENT = "--filter-percent" in sys.argv
FILTER_IQR = "--filter-iqr" in sys.argv

if FILTER_PERCENT:
    print("[compare_logs.py] Outlier filtering using 1% / 99% percent ENABLED")
elif FILTER_IQR:
    print("[compare_logs.py] Outlier filtering using IQR ENABLED")

if len(sys.argv) < 2:
    print("[compare_logs.py] Usage: python3 compare_logs.py <log_folder> [--filter-percent] [--filter-iqr]")
    sys.exit(1)

log_base_folder = os.path.expanduser(sys.argv[1])
if not os.path.isdir(log_base_folder):
    print(f"[compare_logs.py] Error: '{log_base_folder}' is not a valid folder")
    sys.exit(1)

metrics = [
    ("fps", "FPS", True),
    ("frametime", "Frame Time (ms)", False),
    ("cpu_load", "CPU Load (%)", False),
    ("gpu_load", "GPU Load (%)", False)
]

def get_csv_files(game_folder):
    files = sorted(glob.glob(os.path.join(game_folder, '**/eden_*.csv'), recursive=True))
    return [f for f in files if not f.endswith('_summary.csv')]

def read_data(file_path):
    csv_dir = os.path.dirname(file_path)

    version_file = os.path.join(csv_dir, "eden-cli-version.txt")
    name_file = os.path.join(csv_dir, "eden-cli-game-name.txt")
    id_file = os.path.join(csv_dir, "eden-cli-game-id.txt")

    version_short = open(version_file).read().strip().split()[0] if os.path.exists(version_file) else "unknown"
    game_name = open(name_file).read().strip() if os.path.exists(name_file) else os.path.basename(csv_dir)
    game_id = open(id_file).read().strip() if os.path.exists(id_file) else "unknown"

    relative_path = os.path.basename(csv_dir)
    build_folder = os.path.basename(os.path.dirname(csv_dir))

    df = pd.read_csv(file_path, skiprows=2)
    df.columns = df.columns.str.strip()
    summary_file = file_path.replace(".csv", "_summary.csv")

    return {
        "df": df,
        "relative_path": relative_path,
        "build_folder": build_folder,
        "version_short": version_short,
        "summary_file": summary_file,
        "game_name": game_name,
        "game_id": game_id
    }

def build_colors_for_builds(build_folders):
    n = len(build_folders)
    return {b: colorsys.hsv_to_rgb(i / n, 0.7, 0.9) for i, b in enumerate(build_folders)}

def plot_metric(df, column_name, build_colors, build_folder, relative_path, version_short,
                summary_file=None, is_fps=False, ax=None):
    if column_name not in df.columns:
        return None

    y = df[column_name]
    if FILTER_PERCENT:
        lower = y.quantile(0.001)
        upper = y.quantile(0.999)
        y = y.clip(lower=lower, upper=upper)
    elif FILTER_IQR:
        Q1 = y.quantile(0.25)
        Q3 = y.quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR
        y = y.clip(lower=lower, upper=upper)

    x = range(len(y))
    min_val = y.min()
    max_val = y.max()
    avg_val = y.mean()

    summary_text = f"{relative_path:<11} | {version_short:<48} | AVG: {avg_val:>5.1f} | Min: {min_val:>5.1f} | Max: {max_val:>5.1f}"
    if is_fps and summary_file and os.path.exists(summary_file):
        try:
            df_sum = pd.read_csv(summary_file)
            summary_text = (f"{relative_path:<11} | {version_short:<48} | "
                            f"AVG: {float(df_sum['Average FPS'][0]):>5.1f} | "
                            f"Min: {min_val:>5.1f} | Max: {max_val:>5.1f} | "
                            f"0.1%: {float(df_sum['0.1% Min FPS'][0]):>5.1f} | "
                            f"1%: {float(df_sum['1% Min FPS'][0]):>5.1f} | "
                            f"97%: {float(df_sum['97% Percentile FPS'][0]):>5.1f}")
        except Exception as e:
            print(f"[compare_logs.py] Could not read summary for {summary_file}: {e}")

    ax.plot(x, y, label=summary_text, color=build_colors[build_folder])
    return summary_text

def process_game_folder(game_folder):
    csv_files = get_csv_files(game_folder)
    if not csv_files:
        print(f"[compare_logs.py] No CSV files in '{game_folder}', skipping...")
        return

    data = [read_data(f) for f in csv_files]

    game_name = data[0]["game_name"]
    game_id = data[0]["game_id"]
    print(f"[compare_logs.py] Processing game '{game_name}' ({game_id})")

    build_folders = sorted({d['build_folder'] for d in data})
    build_colors = build_colors_for_builds(build_folders)

    png_suffix = "-filtered-percent" if FILTER_PERCENT else "-filtered-iqr" if FILTER_IQR else ""
    title_filter_label = " (Filtered 1%/99% percent)" if FILTER_PERCENT else " (Filtered IQR)" if FILTER_IQR else ""

    for column_name, metric_label, is_fps in metrics:
        plt.figure(figsize=(14, 7))
        ax = plt.gca()

        for d in data:
            plot_metric(
                d['df'], column_name, build_colors, d['build_folder'], d['relative_path'],
                d['version_short'], summary_file=d['summary_file'] if is_fps else None,
                is_fps=is_fps, ax=ax
            )

        plt.xlabel("Frame")
        plt.ylabel(metric_label)
        plt.title(f"{game_name} ({game_id}) - {metric_label} Comparison Across Builds{title_filter_label}")
        plt.legend(fontsize=8)
        plt.grid(True)
        plt.tight_layout()
        plots_dir = os.path.join(game_folder, "plots", column_name)
        os.makedirs(plots_dir, exist_ok=True)
        plt.savefig(os.path.join(plots_dir, f"comparison{png_suffix}.png"), dpi=200)
        plt.close()

    fig, axs = plt.subplots(len(metrics), 1, figsize=(14, 4*len(metrics)), sharex=True)
    for d in data:
        for idx, (col, _, is_fps) in enumerate(metrics):
            plot_metric(
                d['df'], col, build_colors, d['build_folder'], d['relative_path'],
                d['version_short'], summary_file=d['summary_file'] if is_fps else None,
                is_fps=is_fps, ax=axs[idx]
            )

    axs[-1].set_xlabel("Frame")
    for idx, (_, metric_label, _) in enumerate(metrics):
        axs[idx].set_ylabel(metric_label)
        axs[idx].grid(True)
        axs[idx].legend(fontsize=8)

    plt.suptitle(f"{game_name} ({game_id}) - Combined Metrics Comparison Across Builds{title_filter_label}")
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plots_dir = os.path.join(game_folder, "plots", "all_metrics")
    os.makedirs(plots_dir, exist_ok=True)
    plt.savefig(os.path.join(plots_dir, f"comparison{png_suffix}.png"), dpi=200)
    plt.show()

for game_folder in sorted(os.path.join(log_base_folder, d) for d in os.listdir(log_base_folder)
                          if os.path.isdir(os.path.join(log_base_folder, d))):
    process_game_folder(game_folder)
