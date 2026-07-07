#!/usr/bin/env python3
"""
Visual Servoing play script: evaluates VS-Play or VS-Record-Play.

Record mode: manual env.render() viewport (R37 eye/lookat, debug_vis) + wrist TiledCamera.
RecordVideo is not used — it returns gray frames when wrist_cam is in the scene.
"""

import argparse
import os
import random
import sys

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="VS play script with viewport + wrist video recording.")
parser.add_argument("--video", action="store_true", default=True)
parser.add_argument("--no_video", action="store_true", default=False)
parser.add_argument("--video_length", type=int, default=None)
parser.add_argument("--num_episodes", type=int, default=10)
parser.add_argument("--num_envs", type=int, default=None)
parser.add_argument("--task", type=str, default="Isaac-Reach-Franka-VS-Play-v0")
parser.add_argument("--agent", type=str, default=None)
parser.add_argument("--checkpoint", type=str, default=None)
parser.add_argument("--seed", type=int, default=None)
parser.add_argument("--algorithm", type=str, default="SAC")
parser.add_argument("--view", type=str, default="perspective",
                    choices=["perspective", "top", "side", "front"])
parser.add_argument("--ml_framework", type=str, default="torch", choices=["torch", "jax"])
parser.add_argument("--hold_pos_threshold", type=float, default=0.025,
                    help="Zero actions when EE-target distance below this (m).")
parser.add_argument("--hold_image_threshold", type=float, default=0.03,
                    help="Zero actions when image_error L2 norm below this.")
parser.add_argument("--no_hold", action="store_true", help="Disable hold-at-goal policy.")
parser.add_argument("--stillness_threshold", type=float, default=None,
                    help="Deprecated: maps to --hold_image_threshold if set.")

AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()

record_video = args_cli.video and not args_cli.no_video
if record_video:
    args_cli.enable_cameras = True

sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import torch
import gymnasium as gym
import skrl
from packaging import version

SKRL_VERSION = "2.0.0"
if version.parse(skrl.__version__) < version.parse(SKRL_VERSION):
    skrl.logger.error(f"Unsupported skrl version: {skrl.__version__}")
    exit()

from skrl.utils.runner.torch import Runner
from isaaclab.envs import ManagerBasedRLEnvCfg, DirectRLEnvCfg, DirectMARLEnvCfg

from isaaclab_rl.skrl import SkrlVecEnvWrapper
import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils import get_checkpoint_path
from isaaclab_tasks.utils.hydra import hydra_task_config

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vs_video_utils import (
    apply_hold_policy,
    get_base_env,
    get_pos_error_m,
    grab_wrist_frame,
    make_composite,
    print_checkpoint_summary,
    render_viewport_frame,
    setup_r37_viewer,
    write_video_from_frames,
)

if args_cli.agent is None:
    algorithm = args_cli.algorithm.lower()
    agent_cfg_entry_point = "skrl_cfg_entry_point" if algorithm in ["ppo"] else f"skrl_{algorithm}_cfg_entry_point"
else:
    agent_cfg_entry_point = args_cli.agent
    algorithm = agent_cfg_entry_point.split("_cfg")[0].split("skrl_")[-1].lower()

if args_cli.stillness_threshold is not None:
    args_cli.hold_image_threshold = args_cli.stillness_threshold


def _compute_steps_per_episode(env_cfg) -> int:
    dt = env_cfg.sim.dt
    decimation = env_cfg.decimation
    episode_s = env_cfg.episode_length_s
    return int(episode_s / (dt * decimation))


@hydra_task_config(args_cli.task, agent_cfg_entry_point)
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, experiment_cfg: dict):
    if record_video and "Record-Play" not in args_cli.task:
        print("[WARN] Video recording expects --task Isaac-Reach-Franka-VS-Record-Play-v0")

    setup_r37_viewer(env_cfg, args_cli.view)

    env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
    env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device

    if args_cli.seed == -1:
        args_cli.seed = random.randint(0, 10000)
    experiment_cfg["seed"] = args_cli.seed if args_cli.seed is not None else experiment_cfg["seed"]
    env_cfg.seed = experiment_cfg["seed"]

    steps_per_ep = _compute_steps_per_episode(env_cfg)
    num_episodes = args_cli.num_episodes
    total_video_steps = args_cli.video_length if args_cli.video_length else num_episodes * steps_per_ep
    print(f"[INFO] Steps/ep: {steps_per_ep} | Episodes: {num_episodes} | Video steps: {total_video_steps}")

    log_root_path = os.path.abspath(os.path.join("logs", "skrl", experiment_cfg["agent"]["experiment"]["directory"]))

    if args_cli.checkpoint:
        resume_path = os.path.abspath(args_cli.checkpoint)
    else:
        resume_path = get_checkpoint_path(
            log_root_path, run_dir=f".*_{algorithm}_{args_cli.ml_framework}", other_dirs=["checkpoints"]
        )
    log_dir = os.path.dirname(os.path.dirname(resume_path))

    print(f"[INFO] Checkpoint: {resume_path}")
    print_checkpoint_summary(resume_path)

    video_out_dir = os.path.join(log_dir, "videos", "play_vs")
    if record_video:
        os.makedirs(video_out_dir, exist_ok=True)

    render_mode = "rgb_array" if record_video else None
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode=render_mode)
    if record_video:
        print(f"[INFO] Viewport frames -> {video_out_dir}/perspective.mp4 (manual env.render)")

    env_skrl = SkrlVecEnvWrapper(env, ml_framework=args_cli.ml_framework)

    experiment_cfg["trainer"]["close_environment_at_exit"] = False
    experiment_cfg["agent"]["experiment"]["write_interval"] = 0
    experiment_cfg["agent"]["experiment"]["checkpoint_interval"] = 0
    _off_policy = {"sac", "ddpg", "td3"}
    if experiment_cfg.get("agent", {}).get("class", "").lower() in _off_policy:
        experiment_cfg["agent"].pop("rollouts", None)
    runner = Runner(env_skrl, experiment_cfg)

    if experiment_cfg.get("agent", {}).get("class", "").lower() in _off_policy:
        from sac_tanh_squashing import apply_tanh_squashing, apply_alpha_clamp
        apply_tanh_squashing(runner.agent.policy)
        apply_alpha_clamp(runner.agent, alpha_min=0.01)

    runner.agent.load(resume_path)
    runner.agent.enable_training_mode(False, apply_to_models=True)

    base_env = get_base_env(env_skrl)
    has_wrist_cam = "wrist_cam" in base_env.scene.keys() if hasattr(base_env, "scene") else False
    print(f"[INFO] Wrist camera: {has_wrist_cam} | Hold: pos<{args_cli.hold_pos_threshold}m "
          f"or img<{args_cli.hold_image_threshold}")

    obs, _ = env_skrl.reset()
    states = env_skrl.state()

    n_envs = env_cfg.scene.num_envs
    episode_rewards = torch.zeros(n_envs, device=obs.device)
    all_episode_returns = []
    all_final_pos_errors: list[float] = []
    wrist_frames: list = []
    perspective_frames: list = []
    timestep = 0
    hold_enabled = not args_cli.no_hold

    print(f"\n{'='*60}")
    print(f"  VS Evaluation: {num_episodes} episodes | task: {args_cli.task}")
    print(f"{'='*60}")

    while simulation_app.is_running():
        pos_err_pre_step = get_pos_error_m(base_env)

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

        if record_video:
            pframe = render_viewport_frame(env)
            if pframe is not None:
                perspective_frames.append(pframe)
            if has_wrist_cam:
                frame = grab_wrist_frame(base_env, env_idx=0)
                if frame is not None:
                    wrist_frames.append(frame)

        episode_rewards += rewards.squeeze(-1) if rewards.dim() > 1 else rewards
        timestep += 1

        dones = (terminated | truncated).squeeze(-1) if terminated.dim() > 1 else (terminated | truncated)
        done_indices = dones.nonzero(as_tuple=False).squeeze(-1)

        if done_indices.numel() > 0:
            for idx in done_indices:
                i = idx.item()
                ep_ret = episode_rewards[i].item()
                all_episode_returns.append(ep_ret)
                if pos_err_pre_step is not None:
                    all_final_pos_errors.append(pos_err_pre_step[i].item())
                global_ep = len(all_episode_returns)
                pos_str = (f"  PosErr: {pos_err_pre_step[i].item()*100:.1f} cm"
                           if pos_err_pre_step is not None else "")
                print(f"  Episode {global_ep:3d} (env {i}) | Return: {ep_ret:+.4f}{pos_str}")
                episode_rewards[i] = 0.0

        if len(all_episode_returns) >= num_episodes:
            break

        if record_video and timestep >= total_video_steps:
            break

    returns = all_episode_returns[:num_episodes]
    pos_errors = all_final_pos_errors[:num_episodes]
    if returns:
        import statistics
        mean_ret = statistics.mean(returns)
        std_ret = statistics.stdev(returns) if len(returns) > 1 else 0.0
        print(f"\n{'='*60}")
        print(f"  Evaluation Summary ({len(returns)} episodes)")
        print(f"  Mean Return : {mean_ret:+.4f} +/- {std_ret:.4f}")
        print(f"  Min  Return : {min(returns):+.4f}")
        print(f"  Max  Return : {max(returns):+.4f}")
        print(f"  Total Steps : {timestep}")
        if pos_errors:
            mean_pos_cm = statistics.mean(pos_errors) * 100.0
            std_pos_cm = (statistics.stdev(pos_errors) if len(pos_errors) > 1 else 0.0) * 100.0
            threshold_cm = 3.5
            qualified = mean_pos_cm < threshold_cm
            print(f"  Mean Final Pos Error : {mean_pos_cm:.2f} cm +/- {std_pos_cm:.2f} cm")
            print(f"  Threshold            : {threshold_cm} cm  ->  "
                  f"{'QUALIFIED' if qualified else 'NOT QUALIFIED'}")
        print(f"{'='*60}\n")

    if record_video:
        fps = 1.0 / (env_cfg.sim.dt * env_cfg.decimation)
        persp_mp4 = os.path.join(video_out_dir, "perspective.mp4")
        wrist_mp4 = os.path.join(video_out_dir, "wrist_cam.mp4")
        composite_mp4 = os.path.join(video_out_dir, "composite.mp4")

        if perspective_frames:
            write_video_from_frames(perspective_frames, persp_mp4, fps=fps)
        if wrist_frames:
            write_video_from_frames(wrist_frames, wrist_mp4, fps=fps)
        if os.path.isfile(persp_mp4) and wrist_frames:
            make_composite(persp_mp4, wrist_mp4, composite_mp4)

    env_skrl.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
