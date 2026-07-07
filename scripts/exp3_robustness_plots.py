#!/usr/bin/env python3
"""Experiment 3: Robustness verification plots.

Generates thesis-quality robustness figures from JSON results.
"""

import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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

TABLE_DIR = "/home/krz/isaaclab_ws/outputs/tables"
OUT_DIR = "/home/krz/isaaclab_ws/outputs/plots"


def load_json(name):
    with open(os.path.join(TABLE_DIR, name), "r") as f:
        return json.load(f)


def plot_robustness_grid():
    """2x2 subplot grid for all robustness tests."""

    noise = load_json("robustness_noise.json")
    init_pose = load_json("robustness_init_pose.json")
    workspace = load_json("robustness_workspace.json")
    action_perturb = load_json("robustness_action_perturb.json")

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))

    # 1. Observation Noise
    ax = axes[0, 0]
    labels = [r["label"] for r in noise]
    means = [r["mean"] for r in noise]
    stds = [r["std"] for r in noise]
    x = np.arange(len(labels))
    ax.errorbar(x, means, yerr=stds, marker="o", color="C0", linewidth=1.5,
                capsize=4, markersize=6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_xlabel("Observation Noise Magnitude")
    ax.set_ylabel("Mean Return")
    ax.set_title("(a) Observation Noise")
    ax.grid(True, alpha=0.3)
    ax.axhline(y=means[0]*0.5, color="red", linestyle="--", linewidth=0.8,
               alpha=0.5, label="50% degradation")
    ax.legend()

    # 2. Initial Pose Distribution
    ax = axes[0, 1]
    labels = [r["label"] for r in init_pose]
    means = [r["mean"] for r in init_pose]
    stds = [r["std"] for r in init_pose]
    x = np.arange(len(labels))
    ax.errorbar(x, means, yerr=stds, marker="s", color="C1", linewidth=1.5,
                capsize=4, markersize=6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_xlabel("Joint Position Reset Range")
    ax.set_ylabel("Mean Return")
    ax.set_title("(b) Initial Pose Distribution")
    ax.grid(True, alpha=0.3)

    # 3. Action Perturbation
    ax = axes[1, 0]
    labels = [r["label"] for r in action_perturb]
    means = [r["mean"] for r in action_perturb]
    stds = [r["std"] for r in action_perturb]
    x = np.arange(len(labels))
    ax.errorbar(x, means, yerr=stds, marker="^", color="C2", linewidth=1.5,
                capsize=4, markersize=6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_xlabel("Action Perturbation Delta")
    ax.set_ylabel("Mean Return")
    ax.set_title("(c) Action Execution Perturbation")
    ax.grid(True, alpha=0.3)

    # 4. Workspace Expansion
    ax = axes[1, 1]
    labels = [r["label"] for r in workspace]
    means = [r["mean"] for r in workspace]
    stds = [r["std"] for r in workspace]
    x = np.arange(len(labels))
    bars = ax.bar(x, means, yerr=stds, color=["C4", "C5", "C6"],
                  edgecolor="black", linewidth=0.5, capsize=4)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Mean Return")
    ax.set_title("(d) Workspace Range Expansion")
    ax.grid(True, alpha=0.3, axis="y")
    for bar, val in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + 0.5,
                f"{val:+.1f}", ha="center", va="bottom", fontsize=9)

    fig.suptitle("Robustness Verification: Mean Return Under Various Perturbations",
                 fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    path = os.path.join(OUT_DIR, "exp3_robustness_grid.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    plot_robustness_grid()
    print("\nExperiment 3: Robustness plots generated.")
