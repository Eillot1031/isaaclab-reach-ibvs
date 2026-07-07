#!/usr/bin/env python3
"""Experiment 1: Cross-round SAC training process analysis.

Generates thesis-quality figures from existing TensorBoard data across
key training rounds (R29, R32, R35, R36, R37).
"""

import os
import sys
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

ROUNDS = {
    "R29": "2026-05-11_15-40-16_sac_torch",
    "R32": "2026-05-11_18-04-15_sac_torch",
    "R35": "2026-05-13_11-14-14_sac_torch",
    "R36": "2026-05-13_16-39-29_sac_torch",
    "R37": "2026-05-13_21-11-26_sac_torch",
}


def load_scalar(ea, tag):
    events = ea.Scalars(tag)
    steps = [e.step for e in events]
    values = [e.value for e in events]
    return np.array(steps), np.array(values)


def load_round(name):
    run_dir = os.path.join(LOG_BASE, ROUNDS[name])
    ef = [f for f in os.listdir(run_dir) if f.startswith("events.")]
    ea = EventAccumulator(os.path.join(run_dir, ef[0]))
    ea.Reload()
    return ea


def smooth(values, weight=0.9):
    smoothed = np.zeros_like(values)
    last = values[0]
    for i, v in enumerate(values):
        last = weight * last + (1 - weight) * v
        smoothed[i] = last
    return smoothed


def k_formatter(x, pos):
    if x >= 1000:
        return f"{x/1000:.0f}k"
    return f"{x:.0f}"


# ---- Figure 1: R37 detailed training curves (multi-panel) ----
def plot_r37_training_detail():
    ea = load_round("R37")
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))

    # 1. Total reward
    ax = axes[0, 0]
    s, v = load_scalar(ea, "Reward / Total reward (mean)")
    ax.plot(s, v, alpha=0.3, color="C0", linewidth=0.5)
    ax.plot(s, smooth(v), color="C0", linewidth=1.5)
    ax.set_title("Episode Reward (Mean)")
    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Reward")
    ax.xaxis.set_major_formatter(FuncFormatter(k_formatter))

    # 2. Critic loss
    ax = axes[0, 1]
    s, v = load_scalar(ea, "Loss / Critic loss")
    ax.plot(s, v, alpha=0.3, color="C1", linewidth=0.5)
    ax.plot(s, smooth(v), color="C1", linewidth=1.5)
    ax.set_title("Critic Loss")
    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Loss")
    ax.xaxis.set_major_formatter(FuncFormatter(k_formatter))

    # 3. Policy loss
    ax = axes[0, 2]
    s, v = load_scalar(ea, "Loss / Policy loss")
    ax.plot(s, v, alpha=0.3, color="C2", linewidth=0.5)
    ax.plot(s, smooth(v), color="C2", linewidth=1.5)
    ax.set_title("Policy Loss")
    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Loss")
    ax.xaxis.set_major_formatter(FuncFormatter(k_formatter))

    # 4. Alpha (Entropy Coefficient)
    ax = axes[1, 0]
    try:
        s, v = load_scalar(ea, "Coefficient / Entropy coefficient")
    except KeyError:
        s, v = load_scalar(ea, "Loss / Entropy loss")
    ax.plot(s, v, color="C3", linewidth=1.5)
    ax.set_title("Entropy Coefficient (Alpha)")
    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Alpha")
    ax.xaxis.set_major_formatter(FuncFormatter(k_formatter))

    # 5. Position tracking
    ax = axes[1, 1]
    s, v = load_scalar(ea, "Episode_Reward/end_effector_position_tracking")
    ax.plot(s, v, alpha=0.3, color="C4", linewidth=0.5)
    ax.plot(s, smooth(v), color="C4", linewidth=1.5, label="position (L2)")
    s2, v2 = load_scalar(ea, "Episode_Reward/end_effector_position_tracking_fine_grained")
    ax.plot(s2, v2, alpha=0.3, color="C5", linewidth=0.5)
    ax.plot(s2, smooth(v2), color="C5", linewidth=1.5, label="fine-grained (tanh)")
    ax.set_title("Position Tracking Rewards")
    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Episode Reward")
    ax.legend(loc="best")
    ax.xaxis.set_major_formatter(FuncFormatter(k_formatter))

    # 6. reach_success
    ax = axes[1, 2]
    s, v = load_scalar(ea, "Episode_Reward/reach_success")
    ax.plot(s, v, color="C6", linewidth=1.5)
    ax.set_title("Reach Success Bonus")
    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Episode Reward")
    ax.xaxis.set_major_formatter(FuncFormatter(k_formatter))

    fig.suptitle("Round 37 SAC Training Detail (50k iter, IK-Rel)", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    path = os.path.join(OUT_DIR, "exp1_r37_training_detail.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


# ---- Figure 2: Cross-round reward comparison ----
def plot_cross_round_reward():
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = {"R29": "C0", "R32": "C1", "R35": "C2", "R36": "C3", "R37": "C4"}

    for name in ["R29", "R32", "R35", "R36", "R37"]:
        ea = load_round(name)
        s, v = load_scalar(ea, "Reward / Total reward (mean)")
        ax.plot(s, smooth(v, 0.95), label=name, color=colors[name], linewidth=1.5)

    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Mean Episode Reward")
    ax.set_title("Cross-Round Training Reward Comparison")
    ax.legend(loc="best")
    ax.xaxis.set_major_formatter(FuncFormatter(k_formatter))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = os.path.join(OUT_DIR, "exp1_cross_round_reward.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


# ---- Figure 3: R37 per-component reward breakdown ----
def plot_r37_reward_components():
    ea = load_round("R37")
    components = {
        "Position (L2)": "Episode_Reward/end_effector_position_tracking",
        "Position (tanh)": "Episode_Reward/end_effector_position_tracking_fine_grained",
        "Orientation": "Episode_Reward/end_effector_orientation_tracking",
        "Reach Success": "Episode_Reward/reach_success",
        "Action Rate": "Episode_Reward/action_rate",
        "Joint Vel": "Episode_Reward/joint_vel",
    }

    fig, ax = plt.subplots(figsize=(10, 5))
    for i, (label, tag) in enumerate(components.items()):
        s, v = load_scalar(ea, tag)
        ax.plot(s, smooth(v, 0.9), label=label, color=f"C{i}", linewidth=1.5)

    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Per-Episode Reward Component")
    ax.set_title("Round 37: Reward Component Breakdown")
    ax.legend(loc="best", ncol=2)
    ax.xaxis.set_major_formatter(FuncFormatter(k_formatter))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = os.path.join(OUT_DIR, "exp1_r37_reward_components.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


# ---- Figure 4: Cross-round evaluation bar chart ----
def plot_cross_round_eval_bar():
    rounds = ["R29", "R32", "R35", "R36", "R37"]
    mean_returns = [-1.6316, -1.0973, -0.9685, 3.3122, 15.6599]
    pos_errors_cm = [22.0, 19.0, 21.0, 8.0, 3.5]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

    x = np.arange(len(rounds))
    bars1 = ax1.bar(x, mean_returns, color=["C0", "C1", "C2", "C3", "C4"], edgecolor="black", linewidth=0.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(rounds)
    ax1.set_ylabel("Mean Return (10 episodes)")
    ax1.set_title("Evaluation: Mean Return")
    ax1.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
    for bar, val in zip(bars1, mean_returns):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                 f"{val:+.2f}", ha="center", va="bottom", fontsize=8)

    bars2 = ax2.bar(x, pos_errors_cm, color=["C0", "C1", "C2", "C3", "C4"], edgecolor="black", linewidth=0.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(rounds)
    ax2.set_ylabel("Avg Position Error (cm)")
    ax2.set_title("Evaluation: Position Error")
    ax2.axhline(y=5.0, color="red", linestyle="--", linewidth=1.0, label="Target: 5cm")
    ax2.legend(loc="upper right")
    for bar, val in zip(bars2, pos_errors_cm):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                 f"{val:.1f}", ha="center", va="bottom", fontsize=8)

    fig.suptitle("Cross-Round Performance Evolution", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    path = os.path.join(OUT_DIR, "exp1_cross_round_eval_bar.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


# ---- Figure 5: R37 reach_success trajectory detail ----
def plot_reach_success_trajectory():
    ea = load_round("R37")
    s, v = load_scalar(ea, "Episode_Reward/reach_success")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(s, v, color="C6", linewidth=1.5)
    ax.fill_between(s, 0, v, alpha=0.15, color="C6")
    ax.set_xlabel("Training Steps")
    ax.set_ylabel("Reach Success (per-episode)")
    ax.set_title("Round 37: Reach Success Bonus Trajectory")
    ax.xaxis.set_major_formatter(FuncFormatter(k_formatter))
    ax.grid(True, alpha=0.3)

    milestones = [(80000, 0.00), (200000, 0.21), (300000, 0.68), (400000, 0.74)]
    for step, val in milestones:
        ax.annotate(f"{val*100:.0f}%", xy=(step, val), fontsize=8,
                    textcoords="offset points", xytext=(5, 10),
                    arrowprops=dict(arrowstyle="->", color="gray", lw=0.8))

    fig.tight_layout()
    path = os.path.join(OUT_DIR, "exp1_reach_success_trajectory.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    plot_r37_training_detail()
    plot_cross_round_reward()
    plot_r37_reward_components()
    plot_cross_round_eval_bar()
    plot_reach_success_trajectory()
    print("\nExperiment 1: All plots generated.")
