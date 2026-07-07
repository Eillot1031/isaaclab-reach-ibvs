#!/usr/bin/env python3
"""
Post-training plotting script for SKRL SAC training on Isaac-Reach-Franka-v0.

Parses TensorBoard event files from a SKRL training run and generates
matplotlib figures for the four key metrics:
  - Episode Reward
  - Critic Loss (mean of Q1 + Q2)
  - Actor (Policy) Loss
  - Entropy Coefficient (Alpha)

Usage:
    python scripts/plot_skrl_metrics.py --log_dir <path_to_run_dir>
    python scripts/plot_skrl_metrics.py --log_dir IsaacLab/logs/skrl/reach_franka_sac/2026-xx-xx_sac_torch

Output:
    <log_dir>/plots/training_metrics.png   (combined 4-panel figure)
    <log_dir>/plots/episode_reward.png
    <log_dir>/plots/critic_loss.png
    <log_dir>/plots/actor_loss.png
    <log_dir>/plots/alpha.png
"""

import argparse
import os
import glob

import matplotlib
matplotlib.use("Agg")  # headless backend
import matplotlib.pyplot as plt
import numpy as np

from tensorboard.backend.event_processing import event_accumulator


# ---------------------------------------------------------------------------
# Tag mappings: SKRL SAC logs these TensorBoard scalar tags
# ---------------------------------------------------------------------------
# Reward tags (SKRL may use different names depending on version)
REWARD_TAGS = [
    "Reward / Instantaneous reward (mean)",
    "Reward/Instantaneous reward (mean)",
    "Episode / Instantaneous reward (mean)",
    "Reward / Total reward (mean)",
    "Reward/mean_reward",
    "reward",
]

CRITIC_LOSS_TAGS = [
    "Loss / Critic loss",
    "Loss/Critic loss",
    "Loss / Critic 1 loss",
    "Loss/critic_loss",
    "critic_loss",
]

ACTOR_LOSS_TAGS = [
    "Loss / Policy loss",
    "Loss/Policy loss",
    "Loss / Actor loss",
    "Loss/actor_loss",
    "policy_loss",
]

ALPHA_TAGS = [
    "Coefficient / Entropy coefficient",
    "Coefficient/Entropy coefficient",
    "Coefficient / entropy_coefficient",
    "alpha",
    "entropy_coef",
]


def load_events(event_file: str) -> event_accumulator.EventAccumulator:
    ea = event_accumulator.EventAccumulator(
        event_file,
        size_guidance={event_accumulator.SCALARS: 0},  # load all
    )
    ea.Reload()
    return ea


def get_scalar(ea: event_accumulator.EventAccumulator, candidate_tags: list[str]):
    """Return (steps, values) for the first matching tag, or (None, None)."""
    available = ea.Tags().get("scalars", [])
    for tag in candidate_tags:
        if tag in available:
            events = ea.Scalars(tag)
            steps = np.array([e.step for e in events])
            values = np.array([e.value for e in events])
            return steps, values, tag
    return None, None, None


def smooth(values: np.ndarray, window: int = 10) -> np.ndarray:
    """Simple moving-average smoothing."""
    if len(values) < window:
        return values
    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="same")


def find_event_file(log_dir: str) -> str:
    """Find the TensorBoard event file inside log_dir."""
    patterns = [
        os.path.join(log_dir, "events.out.tfevents.*"),
        os.path.join(log_dir, "**", "events.out.tfevents.*"),
    ]
    for pattern in patterns:
        files = sorted(glob.glob(pattern, recursive=True))
        if files:
            return files[0]
    raise FileNotFoundError(
        f"No TensorBoard event file found in '{log_dir}'. "
        "Please verify --log_dir points to the training run directory."
    )


def plot_metric(ax, steps, values, title, ylabel, color, smooth_window=20):
    if steps is None:
        ax.text(0.5, 0.5, "Data not found", ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="gray")
        ax.set_title(title)
        return
    raw_alpha = 0.3
    ax.plot(steps, values, alpha=raw_alpha, color=color, linewidth=0.8)
    if len(values) >= smooth_window:
        ax.plot(steps, smooth(values, smooth_window), color=color, linewidth=1.8, label="smoothed")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel("Environment Steps")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def main():
    parser = argparse.ArgumentParser(description="Plot SKRL SAC training metrics from TensorBoard events.")
    parser.add_argument(
        "--log_dir", type=str, required=True,
        help="Path to the SKRL training run directory (contains events.out.tfevents.* file)."
    )
    parser.add_argument("--smooth_window", type=int, default=20, help="Moving-average window size.")
    args = parser.parse_args()

    log_dir = os.path.abspath(args.log_dir)
    if not os.path.isdir(log_dir):
        print(f"[ERROR] log_dir not found: {log_dir}")
        return

    # Find event file
    try:
        event_file = find_event_file(log_dir)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return
    print(f"[INFO] Loading TensorBoard events from: {event_file}")

    ea = load_events(event_file)
    available_tags = ea.Tags().get("scalars", [])
    print(f"[INFO] Available scalar tags ({len(available_tags)}):")
    for tag in available_tags:
        print(f"  {tag}")

    # Extract metrics
    rew_steps, rew_vals, rew_tag = get_scalar(ea, REWARD_TAGS)
    cri_steps, cri_vals, cri_tag = get_scalar(ea, CRITIC_LOSS_TAGS)
    act_steps, act_vals, act_tag = get_scalar(ea, ACTOR_LOSS_TAGS)
    alp_steps, alp_vals, alp_tag = get_scalar(ea, ALPHA_TAGS)

    print(f"\n[INFO] Matched tags:")
    print(f"  Reward          : {rew_tag}")
    print(f"  Critic Loss     : {cri_tag}")
    print(f"  Actor Loss      : {act_tag}")
    print(f"  Entropy (Alpha) : {alp_tag}")

    # Create output directory
    plot_dir = os.path.join(log_dir, "plots")
    os.makedirs(plot_dir, exist_ok=True)

    # -----------------------------------------------------------------------
    # Combined 4-panel figure
    # -----------------------------------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("SKRL SAC Training Metrics — Isaac-Reach-Franka-v0", fontsize=14, fontweight="bold", y=1.01)

    plot_metric(axes[0, 0], rew_steps, rew_vals, "Episode Reward", "Reward", "#2196F3", args.smooth_window)
    plot_metric(axes[0, 1], cri_steps, cri_vals, "Critic Loss", "Loss", "#F44336", args.smooth_window)
    plot_metric(axes[1, 0], act_steps, act_vals, "Actor (Policy) Loss", "Loss", "#4CAF50", args.smooth_window)
    plot_metric(axes[1, 1], alp_steps, alp_vals, "Entropy Coefficient (Alpha)", "Alpha", "#FF9800", args.smooth_window)

    plt.tight_layout()
    combined_path = os.path.join(plot_dir, "training_metrics.png")
    fig.savefig(combined_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n[INFO] Saved combined plot: {combined_path}")

    # -----------------------------------------------------------------------
    # Individual figures
    # -----------------------------------------------------------------------
    metrics = [
        (rew_steps, rew_vals, "Episode Reward", "Reward", "#2196F3", "episode_reward.png"),
        (cri_steps, cri_vals, "Critic Loss", "Loss", "#F44336", "critic_loss.png"),
        (act_steps, act_vals, "Actor (Policy) Loss", "Loss", "#4CAF50", "actor_loss.png"),
        (alp_steps, alp_vals, "Entropy Coefficient (Alpha)", "Alpha", "#FF9800", "alpha.png"),
    ]

    for steps, vals, title, ylabel, color, fname in metrics:
        fig, ax = plt.subplots(figsize=(8, 4))
        plot_metric(ax, steps, vals, title, ylabel, color, args.smooth_window)
        plt.tight_layout()
        out_path = os.path.join(plot_dir, fname)
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"[INFO] Saved: {out_path}")

    print("\n[INFO] All plots saved to:", plot_dir)


if __name__ == "__main__":
    main()
