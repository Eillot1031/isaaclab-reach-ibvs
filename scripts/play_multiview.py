#!/usr/bin/env python3
"""
Multi-angle play script for Isaac-Reach-Franka using SKRL SAC checkpoint.

Records videos from TWO camera angles (top-down and side view) in a single
Isaac Sim session. Each view runs for --video_length steps, saving an MP4.

Usage:
    cd /home/krz/isaaclab_ws/IsaacLab
    OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab \\
      python ../scripts/play_multiview.py \\
      --checkpoint logs/skrl/reach_franka_sac/<run>/checkpoints/best.pt \\
      --num_envs 4 \\
      --video_length 300

Output (relative to the checkpoint's parent directory):
    videos/play/top_view.mp4   — top-down (bird's-eye) perspective
    videos/play/side_view.mp4  — side perspective (camera from the right)
"""

import argparse
import os
import sys
import time

# ── Must launch Isaac Sim BEFORE importing anything else ──────────────────
from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Multi-angle play with SKRL SAC checkpoint.")
parser.add_argument("--checkpoint", type=str, required=True, help="Path to SKRL checkpoint (.pt file).")
parser.add_argument("--num_envs", type=int, default=4, help="Number of parallel environments.")
parser.add_argument("--video_length", type=int, default=300, help="Steps to record per view.")
parser.add_argument("--task", type=str, default="Isaac-Reach-Franka-IK-Rel-Play-v0", help="Gym task ID.")
parser.add_argument("--seed", type=int, default=42, help="Random seed.")
AppLauncher.add_app_launcher_args(parser)
# Force headless + cameras enabled
args_cli, hydra_args = parser.parse_known_args()
args_cli.headless = True
args_cli.enable_cameras = True

sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# ── Post-launch imports ───────────────────────────────────────────────────
import gymnasium as gym
import torch
import skrl
from skrl.utils.runner.torch import Runner
from isaaclab_rl.skrl import SkrlVecEnvWrapper
import isaaclab_tasks  # noqa: F401 — registers all gym envs
from isaaclab_tasks.utils import get_checkpoint_path
from isaaclab_tasks.utils.hydra import hydra_task_config

# Camera configurations: (eye, lookat, label, output_filename)
CAMERA_VIEWS = [
    {
        "label": "top_view",
        "eye": (0.5, 0.0, 4.0),   # directly above the workspace
        "lookat": (0.5, 0.0, 0.0),
        "filename": "top_view.mp4",
    },
    {
        "label": "side_view",
        "eye": (3.0, 0.0, 1.2),   # from the right side
        "lookat": (0.5, 0.0, 0.5),
        "filename": "side_view.mp4",
    },
]

# SAC experiment config (needed to load runner)
EXPERIMENT_CFG = {
    "seed": args_cli.seed,
    "models": {
        "separate": True,
        "policy": {
            "class": "GaussianMixin",
            "clip_actions": False,
            "clip_log_std": True,
            "min_log_std": -20.0,
            "max_log_std": 0.0,
            "initial_log_std": 0.0,
            "network": [{"name": "net", "input": "OBSERVATIONS", "layers": [512, 256, 128], "activations": "elu"}],
            "output": "ACTIONS",
        },
        "critic_1": {
            "class": "DeterministicMixin",
            "clip_actions": False,
            "network": [{"name": "net", "input": "torch.cat([observations, taken_actions], dim=-1)", "layers": [512, 256, 128], "activations": "elu"}],
            "output": "ONE",
        },
        "critic_2": {
            "class": "DeterministicMixin",
            "clip_actions": False,
            "network": [{"name": "net", "input": "torch.cat([observations, taken_actions], dim=-1)", "layers": [512, 256, 128], "activations": "elu"}],
            "output": "ONE",
        },
        "target_critic_1": {
            "class": "DeterministicMixin",
            "clip_actions": False,
            "network": [{"name": "net", "input": "torch.cat([observations, taken_actions], dim=-1)", "layers": [512, 256, 128], "activations": "elu"}],
            "output": "ONE",
        },
        "target_critic_2": {
            "class": "DeterministicMixin",
            "clip_actions": False,
            "network": [{"name": "net", "input": "torch.cat([observations, taken_actions], dim=-1)", "layers": [512, 256, 128], "activations": "elu"}],
            "output": "ONE",
        },
    },
    "memory": {"class": "RandomMemory", "memory_size": 1},
    "agent": {
        "class": "SAC",
        "gradient_steps": 1,
        "batch_size": 64,
        "discount_factor": 0.99,
        "polyak": 0.005,
        "learning_rate": 5.0e-4,
        "random_timesteps": 0,
        "learning_starts": 0,
        "observation_preprocessor": "RunningStandardScaler",
        "observation_preprocessor_kwargs": {},
        "learn_entropy": True,
        "initial_entropy_value": 0.2,
        "target_entropy": None,
        "experiment": {
            "directory": "",
            "experiment_name": "",
            "write_interval": 0,       # don't write TensorBoard
            "checkpoint_interval": 0,  # don't save checkpoints during play
        },
    },
    "trainer": {
        "class": "SequentialTrainer",
        "timesteps": args_cli.video_length,
        "close_environment_at_exit": False,
    },
}


def record_view(view_cfg: dict, checkpoint_path: str, video_dir: str):
    """Create env with given camera view, load checkpoint, record video."""
    label = view_cfg["label"]
    eye = view_cfg["eye"]
    lookat = view_cfg["lookat"]
    filename = view_cfg["filename"]
    video_path = os.path.join(video_dir, filename)

    print(f"\n{'='*60}")
    print(f"[VIEW] {label}  eye={eye}  lookat={lookat}")
    print(f"{'='*60}")

    # ── Build env config with custom camera ──────────────────────────────
    # Import inside function to allow hydra to be reused
    from isaaclab_tasks.manager_based.manipulation.reach.config.franka.ik_rel_env_cfg import (
        FrankaReachEnvCfg_PLAY,
    )
    env_cfg = FrankaReachEnvCfg_PLAY()
    env_cfg.scene.num_envs = args_cli.num_envs
    env_cfg.seed = args_cli.seed
    env_cfg.viewer.eye = eye
    env_cfg.viewer.lookat = lookat
    env_cfg.log_dir = os.path.dirname(checkpoint_path)

    # ── Create gym env ────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(video_path), exist_ok=True)
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array")
    env = gym.wrappers.RecordVideo(
        env,
        video_folder=video_dir,
        name_prefix=label,
        step_trigger=lambda step: step == 0,
        video_length=args_cli.video_length,
        disable_logger=True,
    )

    # ── Wrap and load checkpoint ──────────────────────────────────────────
    exp_cfg = {**EXPERIMENT_CFG}
    exp_cfg["trainer"]["timesteps"] = args_cli.video_length
    env_skrl = SkrlVecEnvWrapper(env)

    runner = Runner(env_skrl, exp_cfg)
    from sac_tanh_squashing import apply_tanh_squashing, apply_alpha_clamp
    apply_tanh_squashing(runner.agent.policy)
    apply_alpha_clamp(runner.agent, alpha_min=0.01)
    runner.agent.load(checkpoint_path)
    runner.agent.enable_training_mode(False, apply_to_models=True)

    # ── Inference loop ────────────────────────────────────────────────────
    obs, _ = env_skrl.reset()
    states = env_skrl.state()
    for step in range(args_cli.video_length):
        with torch.inference_mode():
            outputs = runner.agent.act(obs, states, timestep=0, timesteps=0)
            actions = outputs[-1].get("mean_actions", outputs[0])
            obs, _, _, _, _ = env_skrl.step(actions)
            states = env_skrl.state()
        if step == args_cli.video_length - 1:
            break

    env_skrl.close()

    # ── Rename the auto-generated video file ─────────────────────────────
    # gym RecordVideo names files as <name_prefix>-episode-0.mp4
    candidate = os.path.join(video_dir, f"{label}-episode-0.mp4")
    if os.path.exists(candidate) and not os.path.exists(video_path):
        os.rename(candidate, video_path)
        print(f"[INFO] Video saved: {video_path}")
    elif os.path.exists(video_path):
        print(f"[INFO] Video saved: {video_path}")
    else:
        print(f"[WARNING] Expected video not found at: {candidate}")
        # List what was created
        created = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]
        print(f"[INFO] Files in {video_dir}: {created}")


def main():
    checkpoint_path = os.path.abspath(args_cli.checkpoint)
    if not os.path.exists(checkpoint_path):
        print(f"[ERROR] Checkpoint not found: {checkpoint_path}")
        simulation_app.close()
        return

    # Video output: sibling directory of checkpoint file
    run_dir = os.path.dirname(os.path.dirname(checkpoint_path))  # …/checkpoints/../
    video_dir = os.path.join(run_dir, "videos", "play_multiview")
    os.makedirs(video_dir, exist_ok=True)
    print(f"[INFO] Videos will be saved to: {video_dir}")
    print(f"[INFO] Checkpoint: {checkpoint_path}")

    for view_cfg in CAMERA_VIEWS:
        record_view(view_cfg, checkpoint_path, video_dir)

    print("\n[INFO] Multi-view recording complete.")
    print(f"[INFO] Output directory: {video_dir}")
    for view_cfg in CAMERA_VIEWS:
        path = os.path.join(video_dir, view_cfg["filename"])
        size_kb = os.path.getsize(path) // 1024 if os.path.exists(path) else 0
        print(f"  {view_cfg['label']}: {path} ({size_kb} KB)")


if __name__ == "__main__":
    main()
    simulation_app.close()
