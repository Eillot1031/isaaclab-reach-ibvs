#!/usr/bin/env python3
"""
Single-view play script for SKRL SAC on Isaac-Reach-Franka.

Supports multi-episode evaluation with per-episode reward logging.
Records a continuous video across all episodes from a specified camera angle.

Usage (from IsaacLab directory):
    cd /home/krz/isaaclab_ws/IsaacLab

    # 10-episode evaluation, perspective view (default)
    OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
        ../scripts/play_view.py \
        --task Isaac-Reach-Franka-Play-v0 \
        --headless --num_envs 4 --algorithm SAC \
        --video --num_episodes 10 \
        --view perspective \
        --checkpoint <path/to/best_agent.pt>

    # Side view
    OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
        ../scripts/play_view.py \
        --task Isaac-Reach-Franka-Play-v0 \
        --headless --num_envs 4 --algorithm SAC \
        --video --num_episodes 10 \
        --view side \
        --checkpoint <path/to/best_agent.pt>
"""

"""Launch Isaac Sim first."""

import argparse
import sys

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Multi-angle play for SKRL SAC.")
parser.add_argument("--video", action="store_true", default=False)
parser.add_argument("--video_length", type=int, default=None,
                    help="Total video length in steps. Overrides num_episodes-based calculation.")
parser.add_argument("--num_episodes", type=int, default=10,
                    help="Number of episodes to evaluate (each ~360 steps). Target resets between episodes.")
parser.add_argument("--num_envs", type=int, default=None)
parser.add_argument("--task", type=str, default="Isaac-Reach-Franka-Play-v0")
parser.add_argument(
    "--agent", type=str, default=None,
    help="Agent config entry point (defaults to algorithm-derived value).",
)
parser.add_argument("--checkpoint", type=str, default=None)
parser.add_argument("--seed", type=int, default=None)
parser.add_argument(
    "--algorithm", type=str, default="SAC",
    help="RL algorithm (e.g. SAC, PPO).",
)
parser.add_argument(
    "--view", type=str, default="perspective",
    choices=["perspective", "top", "side", "front"],
    help="Camera view preset.",
)
parser.add_argument("--ml_framework", type=str, default="torch", choices=["torch", "jax"])
parser.add_argument("--hold_pos_threshold", type=float, default=0.025,
                    help="Zero actions when EE-target distance below this (m).")
parser.add_argument("--hold_image_threshold", type=float, default=0.0,
                    help="Image-error hold (VS only). Default 0 for IK-Rel (31D obs).")
parser.add_argument("--no_hold", action="store_true")
parser.add_argument(
    "--stillness_threshold", type=float, default=None,
    help="Deprecated: maps to --hold_image_threshold.",
)
parser.add_argument("--copy_to_outputs", type=str, default=None,
                    help="If set with --video, copy RecordVideo mp4 to this path after run.")
AppLauncher.add_app_launcher_args(parser)

args_cli, hydra_args = parser.parse_known_args()
if args_cli.video:
    args_cli.enable_cameras = True
sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import os
import random

import gymnasium as gym
import skrl
import torch
from packaging import version

SKRL_VERSION = "2.0.0"
if version.parse(skrl.__version__) < version.parse(SKRL_VERSION):
    skrl.logger.error(f"Unsupported skrl version: {skrl.__version__}")
    exit()

from skrl.utils.runner.torch import Runner
from isaaclab.envs import ManagerBasedRLEnvCfg, DirectRLEnvCfg, DirectMARLEnvCfg
from isaaclab.utils.dict import print_dict

from isaaclab_rl.skrl import SkrlVecEnvWrapper
import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils import get_checkpoint_path
from isaaclab_tasks.utils.hydra import hydra_task_config

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from vs_video_utils import apply_hold_policy, get_base_env

if args_cli.stillness_threshold is not None:
    args_cli.hold_image_threshold = args_cli.stillness_threshold

CAMERA_PRESETS = {
    "perspective": {"eye": (3.5, 3.5, 3.5), "lookat": (0.5, 0.0, 0.5)},
    "top":         {"eye": (0.5, 0.0, 4.0),  "lookat": (0.5, 0.0, 0.0)},
    "side":        {"eye": (3.5, 0.0, 1.5),  "lookat": (0.5, 0.0, 0.5)},
    "front":       {"eye": (0.5, 3.5, 1.5),  "lookat": (0.5, 0.0, 0.5)},
}

if args_cli.agent is None:
    algorithm = args_cli.algorithm.lower()
    agent_cfg_entry_point = "skrl_cfg_entry_point" if algorithm in ["ppo"] else f"skrl_{algorithm}_cfg_entry_point"
else:
    agent_cfg_entry_point = args_cli.agent
    algorithm = agent_cfg_entry_point.split("_cfg")[0].split("skrl_")[-1].lower()


def _compute_steps_per_episode(env_cfg) -> int:
    """Derive steps per episode from env timing config."""
    dt = env_cfg.sim.dt
    decimation = env_cfg.decimation
    episode_s = env_cfg.episode_length_s
    return int(episode_s / (dt * decimation))


@hydra_task_config(args_cli.task, agent_cfg_entry_point)
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, experiment_cfg: dict):
    """Play with a SKRL checkpoint, evaluate multiple episodes, and record video."""

    cam = CAMERA_PRESETS[args_cli.view]
    env_cfg.viewer.eye = cam["eye"]
    env_cfg.viewer.lookat = cam["lookat"]
    print(f"[INFO] Camera view: {args_cli.view} | eye={cam['eye']} | lookat={cam['lookat']}")

    env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
    env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device

    if args_cli.seed == -1:
        args_cli.seed = random.randint(0, 10000)
    experiment_cfg["seed"] = args_cli.seed if args_cli.seed is not None else experiment_cfg["seed"]
    env_cfg.seed = experiment_cfg["seed"]

    steps_per_ep = _compute_steps_per_episode(env_cfg)
    num_episodes = args_cli.num_episodes
    total_video_steps = args_cli.video_length if args_cli.video_length else num_episodes * steps_per_ep
    print(f"[INFO] Steps/episode: {steps_per_ep} | Requested episodes: {num_episodes} | Video steps: {total_video_steps}")

    log_root_path = os.path.join("logs", "skrl", experiment_cfg["agent"]["experiment"]["directory"])
    log_root_path = os.path.abspath(log_root_path)

    if args_cli.checkpoint:
        resume_path = os.path.abspath(args_cli.checkpoint)
    else:
        resume_path = get_checkpoint_path(
            log_root_path, run_dir=f".*_{algorithm}_{args_cli.ml_framework}", other_dirs=["checkpoints"]
        )
    log_dir = os.path.dirname(os.path.dirname(resume_path))
    env_cfg.log_dir = log_dir

    print(f"[INFO] Loading checkpoint: {resume_path}")

    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)

    if args_cli.video:
        video_folder = os.path.join(log_dir, "videos", "play_multiview")
        video_kwargs = {
            "video_folder": video_folder,
            "name_prefix": args_cli.view,
            "step_trigger": lambda step: step == 0,
            "video_length": total_video_steps,
            "disable_logger": True,
        }
        print(f"[INFO] Recording video: {video_folder}/{args_cli.view}-step-0.mp4")
        print_dict(video_kwargs, nesting=4)
        env = gym.wrappers.RecordVideo(env, **video_kwargs)

    env_skrl = SkrlVecEnvWrapper(env, ml_framework=args_cli.ml_framework)

    experiment_cfg["trainer"]["close_environment_at_exit"] = False
    experiment_cfg["agent"]["experiment"]["write_interval"] = 0
    experiment_cfg["agent"]["experiment"]["checkpoint_interval"] = 0
    _off_policy = {"sac", "ddpg", "td3"}
    if experiment_cfg.get("agent", {}).get("class", "").lower() in _off_policy:
        experiment_cfg["agent"].pop("rollouts", None)
    runner = Runner(env_skrl, experiment_cfg)

    # Apply tanh squashing for off-policy algorithms (SAC/DDPG/TD3).
    # Replaces SKRL's hard clip with tanh + Jacobian-corrected log_prob.
    if experiment_cfg.get("agent", {}).get("class", "").lower() in _off_policy:
        import sys as _sys
        _sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
        from sac_tanh_squashing import apply_tanh_squashing, apply_alpha_clamp
        apply_tanh_squashing(runner.agent.policy)
        apply_alpha_clamp(runner.agent, alpha_min=0.01)
        print(f"[INFO] SAC: tanh squashing + alpha clamp (min=0.01) applied")

    print(f"[INFO] Loading checkpoint: {resume_path}")
    runner.agent.load(resume_path)
    runner.agent.enable_training_mode(False, apply_to_models=True)

    base_env = get_base_env(env_skrl)
    hold_enabled = not args_cli.no_hold
    print(f"[INFO] Hold: pos<{args_cli.hold_pos_threshold}m | image<{args_cli.hold_image_threshold}")

    obs, _ = env_skrl.reset()
    states = env_skrl.state()

    n_envs = env_cfg.scene.num_envs
    episode_rewards = torch.zeros(n_envs, device=obs.device)
    episode_counts = torch.zeros(n_envs, dtype=torch.long, device=obs.device)
    all_episode_returns = []
    timestep = 0

    print(f"\n{'='*60}")
    print(f"  Multi-Episode Evaluation: {num_episodes} episodes")
    print(f"{'='*60}")

    while simulation_app.is_running():
        with torch.inference_mode():
            outputs = runner.agent.act(obs, states, timestep=0, timesteps=0)
            actions = outputs[-1].get("mean_actions", outputs[0])
            actions = apply_hold_policy(
                actions, obs, base_env,
                pos_threshold_m=args_cli.hold_pos_threshold,
                image_threshold=args_cli.hold_image_threshold,
                enabled=hold_enabled,
            )

            obs, rewards, terminated, truncated, infos = env_skrl.step(actions)
            states = env_skrl.state()

        episode_rewards += rewards.squeeze(-1) if rewards.dim() > 1 else rewards
        timestep += 1

        dones = (terminated | truncated).squeeze(-1) if terminated.dim() > 1 else (terminated | truncated)
        done_indices = dones.nonzero(as_tuple=False).squeeze(-1)

        if done_indices.numel() > 0:
            for idx in done_indices:
                i = idx.item()
                ep_ret = episode_rewards[i].item()
                ep_num = episode_counts[i].item() + 1
                episode_counts[i] = ep_num
                all_episode_returns.append(ep_ret)
                global_ep = len(all_episode_returns)
                print(f"  Episode {global_ep:3d} (env {i}) | Return: {ep_ret:+.4f}")
                episode_rewards[i] = 0.0

        total_completed = len(all_episode_returns)
        if total_completed >= num_episodes:
            remaining_in_ep = steps_per_ep - (timestep % steps_per_ep)
            if args_cli.video and remaining_in_ep < steps_per_ep:
                for _ in range(remaining_in_ep):
                    with torch.inference_mode():
                        outputs = runner.agent.act(obs, states, timestep=0, timesteps=0)
                        actions = outputs[-1].get("mean_actions", outputs[0])
                        actions = apply_hold_policy(
                            actions, obs, base_env,
                            pos_threshold_m=args_cli.hold_pos_threshold,
                            image_threshold=args_cli.hold_image_threshold,
                            enabled=hold_enabled,
                        )
                        obs, rewards, terminated, truncated, infos = env_skrl.step(actions)
                        states = env_skrl.state()
                    timestep += 1
            break

        if args_cli.video and timestep >= total_video_steps:
            break

    returns = all_episode_returns[:num_episodes]
    if returns:
        import statistics
        mean_ret = statistics.mean(returns)
        std_ret = statistics.stdev(returns) if len(returns) > 1 else 0.0
        min_ret = min(returns)
        max_ret = max(returns)
        print(f"\n{'='*60}")
        print(f"  Evaluation Summary ({len(returns)} episodes)")
        print(f"  Mean Return : {mean_ret:+.4f} +/- {std_ret:.4f}")
        print(f"  Min  Return : {min_ret:+.4f}")
        print(f"  Max  Return : {max_ret:+.4f}")
        print(f"  Total Steps : {timestep}")
        print(f"{'='*60}\n")
    else:
        print("[WARN] No episodes completed during evaluation.")

    env_skrl.close()
    print(f"[INFO] Done. View: {args_cli.view}")

    if args_cli.video and args_cli.copy_to_outputs:
        import shutil
        src = os.path.join(log_dir, "videos", "play_multiview", f"{args_cli.view}-step-0.mp4")
        dst = os.path.abspath(args_cli.copy_to_outputs)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"[INFO] Copied video to {dst}")
        else:
            print(f"[WARN] RecordVideo output not found: {src}")


if __name__ == "__main__":
    main()
    simulation_app.close()
