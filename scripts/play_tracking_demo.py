#!/usr/bin/env python3
"""
连续跟踪演示 — 8字形轨迹；目标写入 pose_command_b（策略观测）+ debug_vis marker。

VS v6 训练为固定目标 reach；本演示为分布外，默认 --traj_freq 120（较慢）。

启动方式：勿使用 ``2>&1 | tail``（Isaac 日志会填满管道导致进程阻塞）。
推荐：``python ... > /tmp/play_tracking_demo.log 2>&1``
"""

import argparse
import sys

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="连续目标跟踪演示录像脚本")
parser.add_argument("--task", type=str, default="Isaac-Reach-Franka-VS-Record-Play-v0")
parser.add_argument("--checkpoint", type=str, default=None)
parser.add_argument("--algorithm", type=str, default="SAC")
parser.add_argument("--agent", type=str, default=None)
parser.add_argument("--num_envs", type=int, default=1)
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--total_steps", type=int, default=600)
parser.add_argument("--traj_freq", type=float, default=120.0,
                    help="轨迹频率：t = step_idx / traj_freq（越大目标变化越慢）")
parser.add_argument("--fps", type=float, default=30.0)
parser.add_argument("--out_video", type=str, default=None)
parser.add_argument("--hold_pos_threshold", type=float, default=0.025)
parser.add_argument("--hold_image_threshold", type=float, default=0.03)
parser.add_argument("--no_hold", action="store_true")
parser.add_argument("--stillness_threshold", type=float, default=None)
parser.add_argument(
    "--render_stride", type=int, default=1,
    help="Capture viewport every N sim steps (1=every step, 2=half rate for debug).",
)
parser.add_argument("--ml_framework", type=str, default="torch", choices=["torch", "jax"])
AppLauncher.add_app_launcher_args(parser)

args_cli, hydra_args = parser.parse_known_args()
args_cli.enable_cameras = True
sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import math
import os
import time

import cv2
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

from isaaclab_rl.skrl import SkrlVecEnvWrapper
import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils import get_checkpoint_path
from isaaclab_tasks.utils.hydra import hydra_task_config

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vs_video_utils import (
    apply_hold_policy,
    encode_h264,
    get_base_env,
    get_pos_error_m,
    print_checkpoint_summary,
    render_viewport_frame,
    setup_r37_viewer,
    write_target_pose_world,
    write_video_from_frames,
)

if args_cli.agent is None:
    algorithm = args_cli.algorithm.lower()
    agent_cfg_entry_point = (
        "skrl_cfg_entry_point" if algorithm == "ppo"
        else f"skrl_{algorithm}_cfg_entry_point"
    )
else:
    agent_cfg_entry_point = args_cli.agent
    algorithm = agent_cfg_entry_point.split("_cfg")[0].split("skrl_")[-1].lower()

if args_cli.stillness_threshold is not None:
    args_cli.hold_image_threshold = args_cli.stillness_threshold


def _lemniscate_target(t: float, cx=0.50, cy=0.00, cz=0.45, ax=0.14, ay=0.10, az=0.06):
    x = cx + ax * math.sin(t)
    y = cy + ay * math.sin(2.0 * t)
    z = cz + az * 0.5 * math.sin(t / 2.0)
    return x, y, z


@hydra_task_config(args_cli.task, agent_cfg_entry_point)
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, experiment_cfg: dict):
    setup_r37_viewer(env_cfg)
    env_cfg.scene.num_envs = args_cli.num_envs
    env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
    env_cfg.seed = args_cli.seed
    experiment_cfg["seed"] = args_cli.seed

    try:
        env_cfg.commands.ee_pose.resampling_time_range = (9999, 9999)
        print("[INFO] Disabled auto command resampling", flush=True)
    except AttributeError:
        print("[WARN] Could not disable command resampling", flush=True)

    if args_cli.out_video:
        out_mp4 = os.path.abspath(args_cli.out_video)
    else:
        os.makedirs("/home/krz/isaaclab_ws/outputs/videos", exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_mp4 = f"/home/krz/isaaclab_ws/outputs/videos/tracking_demo_{ts}.mp4"

    if args_cli.checkpoint:
        resume_path = os.path.abspath(args_cli.checkpoint)
    else:
        log_root_path = os.path.abspath(
            os.path.join("logs", "skrl", experiment_cfg["agent"]["experiment"]["directory"])
        )
        resume_path = get_checkpoint_path(
            log_root_path,
            run_dir=f".*_{algorithm}_{args_cli.ml_framework}",
            other_dirs=["checkpoints"],
        )
    print(f"[INFO] Checkpoint: {resume_path}", flush=True)
    print_checkpoint_summary(resume_path)

    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array")
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
    obs, _ = env_skrl.reset()
    states = env_skrl.state()

    total_steps = args_cli.total_steps
    traj_freq = args_cli.traj_freq
    hold_enabled = not args_cli.no_hold
    frames = []

    render_stride = max(1, args_cli.render_stride)
    print(f"[INFO] Recording {total_steps} steps (lemniscate, traj_freq={traj_freq}, "
          f"render_stride={render_stride})", flush=True)
    print("[INFO] Note: VS v6 was trained for fixed-target reach; tracking is out-of-distribution.",
          flush=True)
    print("[INFO] Do not wrap stdout with '| tail' — use a log file instead.", flush=True)

    for step_idx in range(total_steps):
        t = step_idx / traj_freq
        tx, ty, tz = _lemniscate_target(t)
        write_target_pose_world(base_env, tx, ty, tz)

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

        if step_idx % render_stride == 0:
            frame = render_viewport_frame(env)
            if frame is not None:
                cv2.putText(frame, f"Target: ({tx:.3f}, {ty:.3f}, {tz:.3f})", (10, 32),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 50), 2, cv2.LINE_AA)
                cv2.putText(frame, f"Step {step_idx + 1}/{total_steps}", (10, 62),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 200, 200), 1, cv2.LINE_AA)
                frames.append(frame)

        if step_idx > 0 and step_idx % 60 == 0:
            pe = get_pos_error_m(base_env)
            if pe is not None:
                print(f"  step {step_idx}/{total_steps}: pos_err={pe[0].item()*100:.2f} cm",
                      flush=True)

        if (terminated | truncated).any():
            obs, _ = env_skrl.reset()
            states = env_skrl.state()
            write_target_pose_world(base_env, tx, ty, tz)

    env_skrl.close()

    if not frames:
        print("[WARN] No frames captured.")
        return

    tmp_mp4 = out_mp4.replace(".mp4", "_raw.mp4")
    write_video_from_frames(frames, tmp_mp4, fps=args_cli.fps)
    if encode_h264(tmp_mp4, out_mp4):
        os.remove(tmp_mp4)
    print(f"[INFO] Tracking demo saved: {out_mp4}  ({len(frames)} frames)", flush=True)


if __name__ == "__main__":
    main()
    simulation_app.close()
