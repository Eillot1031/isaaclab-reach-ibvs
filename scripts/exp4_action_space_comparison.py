#!/usr/bin/env python3
"""Experiment 4: Action space comparison -- JointPosition (R32) vs IK-Rel (R37).

Generates thesis-quality comparison figures from existing TensorBoard data.
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
    "legend.fontsize": 10,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

LOG_BASE = "/home/krz/isaaclab_ws/IsaacLab/logs/skrl/reach_franka_sac"
OUT_DIR = "/home/krz/isaaclab_ws/outputs/plots"

RUNS = {
    "R32-JointPace": "2026-05-11_18-04-15_sac_torch",
    "R37-IK-Rel":   "2026-05-13_21-11-26_sac_torch",
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


def load_ea(name):
    run_dir = os.path.join(LOG_BASE, RUNS[name])
    ef = [f for f in os.listdir(run_dir) if f.startswith("events.")]
    ea = EventAccumulator(os.path.join(run_dir, ef[0]))
    ea.Reload()
    return ea


def k_fmt(x, pos):
    return f"{x/1000:.0f}k" if x >= 1000 else f"{x:.0f}"


# ---- Figure 1: Side-by-side training curves ----
def plot_training_comparison():
    ea32 = load_ea("R32-JointPace")
    ea37 = load_ea("R37-IK-Rel")

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))

    # Total reward
    ax = axes[0, 0]
    for ea, label, color in [(ea32, "JointPace (R32)", "C0"), (ea37, "IK-Rel (R37)", "C3")]:
        s, v = load_scalar(ea, "Reward / Total reward (mean)")
        ax.plot(s, smooth(v, 0.95), label=label, color=color, linewidth=1.5)
    ax.set_title("Mean Episode Reward")
    ax.set_ylabel("Reward")
    ax.legend()
    ax.xaxis.set_major_formatter(FuncFormatter(k_fmt))
    ax.grid(True, alpha=0.3)

    # Critic loss
    ax = axes[0, 1]
    for ea, label, color in [(ea32, "JointPace (R32)", "C0"), (ea37, "IK-Rel (R37)", "C3")]:
        s, v = load_scalar(ea, "Loss / Critic loss")
        ax.plot(s, smooth(v, 0.95), label=label, color=color, linewidth=1.5)
    ax.set_title("Critic Loss")
    ax.set_ylabel("Loss")
    ax.legend()
    ax.xaxis.set_major_formatter(FuncFormatter(k_fmt))
    ax.grid(True, alpha=0.3)

    # Position tracking
    ax = axes[1, 0]
    for ea, label, color in [(ea32, "JointPace (R32)", "C0"), (ea37, "IK-Rel (R37)", "C3")]:
        s, v = load_scalar(ea, "Episode_Reward/end_effector_position_tracking")
        ax.plot(s, smooth(v, 0.9), label=label, color=color, linewidth=1.5)
    ax.set_title("Position Tracking (L2 penalty)")
    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Episode Reward")
    ax.legend()
    ax.xaxis.set_major_formatter(FuncFormatter(k_fmt))
    ax.grid(True, alpha=0.3)

    # Alpha
    ax = axes[1, 1]
    tag = "Coefficient / Entropy coefficient"
    for ea, label, color in [(ea32, "JointPace (R32)", "C0"), (ea37, "IK-Rel (R37)", "C3")]:
        try:
            s, v = load_scalar(ea, tag)
        except KeyError:
            s, v = load_scalar(ea, "Loss / Entropy loss")
        ax.plot(s, v, label=label, color=color, linewidth=1.5)
    ax.set_title("Entropy Coefficient (Alpha)")
    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Alpha")
    ax.legend()
    ax.xaxis.set_major_formatter(FuncFormatter(k_fmt))
    ax.grid(True, alpha=0.3)

    fig.suptitle("Action Space Comparison: JointPace vs IK-Rel", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    path = os.path.join(OUT_DIR, "exp4_action_space_training_comparison.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


# ---- Figure 2: Evaluation metrics bar chart ----
def plot_eval_comparison():
    methods = ["JointPace\n(R32)", "IK-Rel\n(R37)"]
    mean_returns = [-1.0973, 15.6599]
    std_returns = [0.6496, 0.5332]
    pos_errors = [19.0, 3.5]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4))

    x = np.arange(2)
    colors = ["C0", "C3"]

    bars1 = ax1.bar(x, mean_returns, yerr=std_returns, color=colors,
                    edgecolor="black", linewidth=0.5, capsize=5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(methods)
    ax1.set_ylabel("Mean Return")
    ax1.set_title("Evaluation: Mean Return (10 eps)")
    ax1.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
    for bar, val, std in zip(bars1, mean_returns, std_returns):
        ax1.text(bar.get_x() + bar.get_width()/2,
                 bar.get_height() + std + 0.5,
                 f"{val:+.2f}", ha="center", va="bottom", fontsize=10, fontweight="bold")

    bars2 = ax2.bar(x, pos_errors, color=colors, edgecolor="black", linewidth=0.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(methods)
    ax2.set_ylabel("Avg Position Error (cm)")
    ax2.set_title("Evaluation: Position Error")
    ax2.axhline(y=5.0, color="red", linestyle="--", linewidth=1.0, label="Target: 5cm")
    ax2.legend()
    for bar, val in zip(bars2, pos_errors):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                 f"{val:.1f} cm", ha="center", va="bottom", fontsize=10, fontweight="bold")

    fig.suptitle("Action Space Comparison: Evaluation Results", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    path = os.path.join(OUT_DIR, "exp4_action_space_eval_comparison.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


# ---- Figure 3: Side-by-side simulation screenshots ----
def plot_screenshot_comparison():
    from PIL import Image

    screenshot_dir = "/home/krz/isaaclab_ws/outputs/screenshots"
    imgs = {
        "R32 Perspective": os.path.join(screenshot_dir, "r32_perspective_frame.png"),
        "R32 Side": os.path.join(screenshot_dir, "r32_side_frame.png"),
        "R37 Perspective": os.path.join(screenshot_dir, "r37_perspective_frame.png"),
        "R37 Side": os.path.join(screenshot_dir, "r37_side_frame.png"),
    }

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    titles = [
        ("JointPace (R32) - Perspective", "r32_perspective_frame.png"),
        ("IK-Rel (R37) - Perspective", "r37_perspective_frame.png"),
        ("JointPace (R32) - Side", "r32_side_frame.png"),
        ("IK-Rel (R37) - Side", "r37_side_frame.png"),
    ]

    for ax, (title, fname) in zip(axes.flat, titles):
        img = Image.open(os.path.join(screenshot_dir, fname))
        ax.imshow(np.array(img))
        ax.set_title(title, fontsize=11)
        ax.axis("off")

    fig.suptitle("Simulation Screenshots: JointPace vs IK-Rel", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    path = os.path.join(OUT_DIR, "exp4_simulation_screenshots.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    plot_training_comparison()
    plot_eval_comparison()
    plot_screenshot_comparison()
    print("\nExperiment 4: All plots generated.")
