#!/usr/bin/env python3
"""Experiment 2: Reward ablation comparison plots.

Generates thesis-quality ablation comparison figures from TensorBoard data.
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

plt.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

LOG_BASE = "/home/krz/isaaclab_ws/IsaacLab/logs/skrl/reach_franka_sac"
OUT_DIR = "/home/krz/isaaclab_ws/outputs/plots"

ABLATIONS = {
    "A0: Full Model\n(Baseline)": "2026-05-13_21-11-26_sac_torch",
    "A1: No Success\nBonus":      "2026-05-18_09-48-55_sac_torch",
    "A2: No Orientation\nTracking": "2026-05-18_11-25-02_sac_torch",
    "A3: No Action\nPenalties":   "2026-05-18_13-02-00_sac_torch",
    "A4: Position\nOnly":         "2026-05-18_14-39-10_sac_torch",
}

EVAL_RESULTS = {
    "A0: Full Model\n(Baseline)": {"mean": 15.6599, "std": 0.5332},
    "A1: No Success\nBonus":      {"mean": 12.0530, "std": 4.6144},
    "A2: No Orientation\nTracking": {"mean": -1.6255, "std": 2.1384},
    "A3: No Action\nPenalties":   {"mean": 15.6720, "std": 0.5035},
    "A4: Position\nOnly":         {"mean": -1.5240, "std": 2.0662},
}


def load_scalar(ea, tag):
    events = ea.Scalars(tag)
    return np.array([e.step for e in events]), np.array([e.value for e in events])


def smooth(values, weight=0.9):
    out = np.zeros_like(values)
    last = values[0]
    for i, v in enumerate(values):
        last = weight * last + (1 - weight) * v
        out[i] = last
    return out


def load_ea(run_dir):
    path = os.path.join(LOG_BASE, run_dir)
    ef = [f for f in os.listdir(path) if f.startswith("events.")]
    ea = EventAccumulator(os.path.join(path, ef[0]))
    ea.Reload()
    return ea


def k_fmt(x, pos):
    return f"{x/1000:.0f}k" if x >= 1000 else f"{x:.0f}"


# ---- Figure 1: Training reward curves comparison ----
def plot_training_curves():
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["C2", "C0", "C1", "C3", "C4"]

    for (name, run_dir), color in zip(ABLATIONS.items(), colors):
        ea = load_ea(run_dir)
        s, v = load_scalar(ea, "Reward / Total reward (mean)")
        label = name.replace("\n", " ")
        ax.plot(s, smooth(v, 0.95), label=label, color=color, linewidth=1.5)

    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Mean Episode Reward")
    ax.set_title("Reward Ablation: Training Curves Comparison")
    ax.legend(loc="best", fontsize=8)
    ax.xaxis.set_major_formatter(FuncFormatter(k_fmt))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = os.path.join(OUT_DIR, "exp2_ablation_training_curves.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


# ---- Figure 2: Evaluation bar chart ----
def plot_eval_bar():
    names = list(EVAL_RESULTS.keys())
    means = [EVAL_RESULTS[n]["mean"] for n in names]
    stds = [EVAL_RESULTS[n]["std"] for n in names]
    colors = ["C2", "C0", "C1", "C3", "C4"]

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(names))
    bars = ax.bar(x, means, yerr=stds, color=colors, edgecolor="black",
                  linewidth=0.5, capsize=4)
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylabel("Mean Return (10 episodes)")
    ax.set_title("Reward Ablation: Evaluation Results")
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)

    for bar, val, std in zip(bars, means, stds):
        y_pos = bar.get_height() + std + 0.5 if val >= 0 else bar.get_height() - std - 1.5
        ax.text(bar.get_x() + bar.get_width()/2, y_pos,
                f"{val:+.2f}", ha="center", va="bottom" if val >= 0 else "top",
                fontsize=9, fontweight="bold")

    fig.tight_layout()
    path = os.path.join(OUT_DIR, "exp2_ablation_eval_bar.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


# ---- Figure 3: Position tracking comparison ----
def plot_position_tracking():
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["C2", "C0", "C1", "C3", "C4"]

    for (name, run_dir), color in zip(ABLATIONS.items(), colors):
        ea = load_ea(run_dir)
        s, v = load_scalar(ea, "Episode_Reward/end_effector_position_tracking")
        label = name.replace("\n", " ")
        ax.plot(s, smooth(v, 0.9), label=label, color=color, linewidth=1.5)

    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Position Tracking Reward (higher = closer)")
    ax.set_title("Reward Ablation: Position Error Comparison")
    ax.legend(loc="best", fontsize=8)
    ax.xaxis.set_major_formatter(FuncFormatter(k_fmt))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = os.path.join(OUT_DIR, "exp2_ablation_position_tracking.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    plot_training_curves()
    plot_eval_bar()
    plot_position_tracking()
    print("\nExperiment 2: All ablation plots generated.")
