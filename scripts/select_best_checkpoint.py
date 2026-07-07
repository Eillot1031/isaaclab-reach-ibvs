#!/usr/bin/env python3
"""
Select the best SKRL checkpoint based on mean episode reward.

Parses the TensorBoard event file for the training run, finds the env step
with the highest smoothed mean reward, then copies the nearest checkpoint
to <log_dir>/checkpoints/best.pt.

Usage:
    python scripts/select_best_checkpoint.py --log_dir <path_to_run_dir>
    python scripts/select_best_checkpoint.py --log_dir IsaacLab/logs/skrl/reach_franka_sac/2026-xx-xx_sac_torch

Output:
    <log_dir>/checkpoints/best.pt   — symlink or copy of the best checkpoint
    Prints which checkpoint was selected and the best reward value.
"""

import argparse
import glob
import os
import shutil

import numpy as np
from tensorboard.backend.event_processing import event_accumulator

# Same reward tag candidates as the plotting script
REWARD_TAGS = [
    "Reward / Instantaneous reward (mean)",
    "Reward/Instantaneous reward (mean)",
    "Episode / Instantaneous reward (mean)",
    "Reward / Total reward (mean)",
    "Reward/mean_reward",
    "reward",
]


def find_event_file(log_dir: str) -> str:
    for pattern in [
        os.path.join(log_dir, "events.out.tfevents.*"),
        os.path.join(log_dir, "**", "events.out.tfevents.*"),
    ]:
        files = sorted(glob.glob(pattern, recursive=True))
        if files:
            return files[0]
    raise FileNotFoundError(f"No TensorBoard event file in '{log_dir}'")


def find_checkpoints(log_dir: str) -> list[tuple[int, str]]:
    """Return list of (step, path) sorted by step ascending."""
    ckpt_dir = os.path.join(log_dir, "checkpoints")
    if not os.path.isdir(ckpt_dir):
        raise FileNotFoundError(f"Checkpoint directory not found: {ckpt_dir}")

    results = []
    for path in glob.glob(os.path.join(ckpt_dir, "agent_*.pt")):
        fname = os.path.basename(path)
        # SKRL saves checkpoints as agent_<step>.pt
        try:
            step = int(fname.replace("agent_", "").replace(".pt", ""))
            results.append((step, path))
        except ValueError:
            continue
    return sorted(results, key=lambda x: x[0])


def smooth(values: np.ndarray, window: int = 10) -> np.ndarray:
    if len(values) < window:
        return values
    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="same")


def main():
    parser = argparse.ArgumentParser(description="Select best SKRL checkpoint by reward.")
    parser.add_argument("--log_dir", type=str, required=True,
                        help="Path to the SKRL training run directory.")
    parser.add_argument("--smooth_window", type=int, default=10,
                        help="Smoothing window for reward (default: 10).")
    args = parser.parse_args()

    log_dir = os.path.abspath(args.log_dir)

    # Load events
    event_file = find_event_file(log_dir)
    print(f"[INFO] Loading TensorBoard events: {event_file}")
    ea = event_accumulator.EventAccumulator(event_file, size_guidance={event_accumulator.SCALARS: 0})
    ea.Reload()

    # Find reward tag
    available = ea.Tags().get("scalars", [])
    rew_tag = None
    for tag in REWARD_TAGS:
        if tag in available:
            rew_tag = tag
            break
    if rew_tag is None:
        print(f"[ERROR] No reward tag found. Available: {available}")
        return

    events = ea.Scalars(rew_tag)
    steps = np.array([e.step for e in events])
    values = np.array([e.value for e in events])
    smoothed = smooth(values, args.smooth_window)

    best_idx = int(np.argmax(smoothed))
    best_step = int(steps[best_idx])
    best_reward = float(smoothed[best_idx])
    print(f"[INFO] Best reward: {best_reward:.4f} at env step {best_step}")

    # Find available checkpoints
    checkpoints = find_checkpoints(log_dir)
    if not checkpoints:
        print(f"[ERROR] No checkpoints found in {log_dir}/checkpoints/")
        return

    ckpt_steps = np.array([s for s, _ in checkpoints])
    nearest_idx = int(np.argmin(np.abs(ckpt_steps - best_step)))
    nearest_step, nearest_path = checkpoints[nearest_idx]
    print(f"[INFO] Nearest checkpoint: step={nearest_step}, path={nearest_path}")

    # Copy to best.pt
    best_dest = os.path.join(log_dir, "checkpoints", "best.pt")
    shutil.copy2(nearest_path, best_dest)
    print(f"[INFO] Saved best checkpoint: {best_dest}")
    print(f"[INFO] Summary: reward={best_reward:.4f} @ step {best_step} → ckpt step {nearest_step}")


if __name__ == "__main__":
    main()
