#!/usr/bin/env python3
"""
IBVS 180° 奇异点鲁棒性测试脚本

传统 IBVS 在相机绕光轴旋转约 π 时失效（4 个特征点呈对称分布，控制器陷入局部极小值）。
本脚本通过直接修改 panda_joint7（索引 6）关节位置 += π，制造奇异初始条件，
然后运行 10 个 episode，验证 RL 模型是否具备克服此问题的能力。

奇异点注入方法（按计划规范）：
    robot = base_env.scene["robot"]
    jp = robot.data.joint_pos.clone()
    jp[:, 6] += math.pi
    robot.write_joint_position_to_sim(jp)
    base_env.sim.step()

后退检测：
    每步记录 EE→target 距离，episode 结束后判断：
    retreat_ratio = (max_dist - initial_dist) / initial_dist
    retreat_flag  = retreat_ratio > 0.10  (后退超过初始距离 10%)
    在视频右上角标注 [OK 直接趋近] 或 [RETREAT XX%]

Usage（从 IsaacLab 目录执行）:
    cd /home/krz/isaaclab_ws/IsaacLab

    OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
        ../scripts/play_singularity_test.py \
        --task Isaac-Reach-Franka-VS-Play-v0 \
        --headless --num_envs 1 --algorithm SAC \
        --checkpoint <path/to/best_agent.pt>

输出：outputs/videos/singularity_test_annotated.mp4
"""

"""Launch Isaac Sim Simulator first."""

import argparse
import sys

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="IBVS 180° 奇异点鲁棒性测试")
parser.add_argument("--task", type=str, default="Isaac-Reach-Franka-VS-Record-Play-v0")
parser.add_argument("--checkpoint", type=str, default=None)
parser.add_argument("--algorithm", type=str, default="SAC")
parser.add_argument("--agent", type=str, default=None)
parser.add_argument("--num_envs", type=int, default=1)
parser.add_argument("--num_episodes", type=int, default=10)
parser.add_argument("--seed", type=int, default=7)
parser.add_argument("--fps", type=float, default=30.0)
parser.add_argument("--out_video", type=str, default=None,
                    help="输出路径，默认 outputs/videos/singularity_test_annotated.mp4")
parser.add_argument("--hold_pos_threshold", type=float, default=0.025)
parser.add_argument("--hold_image_threshold", type=float, default=0.03)
parser.add_argument("--no_hold", action="store_true")
parser.add_argument("--stillness_threshold", type=float, default=None)
parser.add_argument("--settle_steps", type=int, default=15,
                    help="Zero-action steps after singularity injection before policy runs.")
parser.add_argument("--singularity_scale", type=float, default=1.0,
                    help="Scale on joint7 offset (1.0=180deg, 0.5=90deg for demos).")
parser.add_argument(
    "--retreat_threshold", type=float, default=0.10,
    help="EE 最大距离超过初始距离 X 倍时判定为后退（默认 0.10 = 10%%）",
)
parser.add_argument("--ml_framework", type=str, default="torch", choices=["torch", "jax"])
AppLauncher.add_app_launcher_args(parser)

args_cli, hydra_args = parser.parse_known_args()
args_cli.enable_cameras = True
sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# ── 后续导入 ──────────────────────────────────────────────────────────────────
import math
import os
import subprocess
import time

import cv2
import gymnasium as gym
import numpy as np
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


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _inject_singularity(base_env, scale: float = 1.0):
    """Reset 后将 panda_joint7（索引 6）+= π * scale，制造奇异初始条件。"""
    robot = base_env.scene["robot"]
    jp = robot.data.joint_pos.clone()
    jp[:, 6] = jp[:, 6] + math.pi * scale
    robot.write_joint_position_to_sim(jp)
    base_env.sim.step()


def _settle_after_inject(env_skrl, base_env, obs, states, steps: int):
    """Zero-action steps so kinematics/obs stabilize after singularity injection."""
    zero = torch.zeros((base_env.num_envs, base_env.action_manager.total_action_dim),
                       device=obs.device)
    for _ in range(steps):
        with torch.inference_mode():
            obs, _, _, _, _ = env_skrl.step(zero)
            states = env_skrl.state()
    return obs, states


def _compute_steps_per_episode(env_cfg) -> int:
    return int(env_cfg.episode_length_s / (env_cfg.sim.dt * env_cfg.decimation))


def _put_text_right(frame: np.ndarray, lines: list[str], color=(0, 255, 255),
                    scale: float = 0.60, thickness: int = 2) -> np.ndarray:
    """在画面右上角绘制多行文字（带黑色描边）。"""
    frame = frame.copy()
    font = cv2.FONT_HERSHEY_SIMPLEX
    line_h = int(32 * scale)
    for i, line in enumerate(lines):
        (tw, _), _ = cv2.getTextSize(line, font, scale, thickness)
        x = frame.shape[1] - tw - 10
        y = 28 + i * line_h
        cv2.putText(frame, line, (x + 1, y + 1), font, scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
        cv2.putText(frame, line, (x, y), font, scale, color, thickness, cv2.LINE_AA)
    return frame


# ── 主函数 ────────────────────────────────────────────────────────────────────

@hydra_task_config(args_cli.task, agent_cfg_entry_point)
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg,
         experiment_cfg: dict):

    setup_r37_viewer(env_cfg)
    env_cfg.scene.num_envs = args_cli.num_envs
    env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
    env_cfg.seed = args_cli.seed
    experiment_cfg["seed"] = args_cli.seed

    # 输出路径
    os.makedirs("/home/krz/isaaclab_ws/outputs/videos", exist_ok=True)
    if args_cli.out_video:
        final_mp4 = os.path.abspath(args_cli.out_video)
    else:
        final_mp4 = "/home/krz/isaaclab_ws/outputs/videos/singularity_test_annotated.mp4"
    raw_mp4 = final_mp4.replace(".mp4", "_raw.mp4")

    # 检查点
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
    print(f"[INFO] Checkpoint: {resume_path}")
    print_checkpoint_summary(resume_path)

    steps_per_ep = _compute_steps_per_episode(env_cfg)
    num_episodes = args_cli.num_episodes
    if args_cli.stillness_threshold is not None:
        args_cli.hold_image_threshold = args_cli.stillness_threshold
    hold_enabled = not args_cli.no_hold
    retreat_th = args_cli.retreat_threshold
    settle_steps = args_cli.settle_steps
    sing_scale = args_cli.singularity_scale
    print(f"[INFO] Episodes: {num_episodes} x {steps_per_ep} steps")
    print(f"[INFO] Singularity: joint7 += {180.0 * sing_scale:.0f} deg | settle_steps={settle_steps}")

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
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from sac_tanh_squashing import apply_tanh_squashing, apply_alpha_clamp
        apply_tanh_squashing(runner.agent.policy)
        apply_alpha_clamp(runner.agent, alpha_min=0.01)

    runner.agent.load(resume_path)
    runner.agent.enable_training_mode(False, apply_to_models=True)

    base_env = get_base_env(env_skrl)

    # 获取 panda_hand 索引
    hand_id: int = 0
    try:
        hand_id = base_env.scene["robot"].find_bodies("panda_hand")[0][0]
    except Exception:
        pass

    # 首次 reset + 注入奇异
    obs, _ = env_skrl.reset()
    states = env_skrl.state()
    _inject_singularity(base_env, scale=sing_scale)
    obs, states = _settle_after_inject(env_skrl, base_env, obs, states, settle_steps)

    all_ep_returns: list[float] = []
    all_ep_retreat_ratios: list[float] = []   # (max_dist - initial_dist) / initial_dist
    all_ep_final_pos_cm: list[float] = []     # 最终位置误差 (cm)
    ep_reward = torch.zeros(args_cli.num_envs, device=obs.device)
    current_ep = 1
    frames = []

    # 当前 episode 的距离历史
    dist_history: list[float] = []
    initial_dist: float = 0.0

    # 初始距离
    try:
        d0 = get_pos_error_m(base_env, hand_id)[0].item()
        initial_dist = d0
        dist_history.append(d0)
    except Exception:
        pass

    # 当前 episode 在右上角显示的注释行
    ann_lines: list[str] = [
        f"Episode {current_ep}/{num_episodes}",
        "IBVS Singularity Test",
        "Joint7 += 180 deg",
    ]
    ann_color = (0, 255, 255)   # 黄色 → BGR cyan (显示为黄/青)

    print(f"\n{'='*55}")
    print(f"  IBVS 180° 奇异点测试  —  {num_episodes} episodes")
    print(f"{'='*55}")

    while simulation_app.is_running():
        with torch.inference_mode():
            outputs = runner.agent.act(obs, states, timestep=0, timesteps=0)
            actions = outputs[-1].get("mean_actions", outputs[0])
            actions = apply_hold_policy(
                actions, obs, base_env,
                pos_threshold_m=args_cli.hold_pos_threshold,
                image_threshold=args_cli.hold_image_threshold,
                hand_id=hand_id,
                enabled=hold_enabled,
            )
            obs, rewards, terminated, truncated, infos = env_skrl.step(actions)
            states = env_skrl.state()

        ep_reward += rewards.squeeze(-1) if rewards.dim() > 1 else rewards

        # 记录距离
        try:
            d = get_pos_error_m(base_env, hand_id)[0].item()
            dist_history.append(d)
        except Exception:
            pass

        dones = (terminated | truncated).squeeze(-1) if terminated.dim() > 1 else (terminated | truncated)
        if dones.any():
            ep_ret = ep_reward[0].item()
            all_ep_returns.append(ep_ret)

            # 后退分析
            final_dist = dist_history[-1] if dist_history else 0.0
            max_dist = max(dist_history) if dist_history else 0.0
            retreat_ratio = (max_dist - initial_dist) / (initial_dist + 1e-6)
            retreat_flag = retreat_ratio > retreat_th
            all_ep_retreat_ratios.append(retreat_ratio)
            all_ep_final_pos_cm.append(final_dist * 100.0)

            retreat_str = (f"[RETREAT {retreat_ratio*100:.0f}%]"
                           if retreat_flag else "[OK 直接趋近]")
            print(f"  Episode {current_ep:2d}/{num_episodes}  |  "
                  f"Return: {ep_ret:+.4f}  |  "
                  f"FinalPos: {final_dist*100:.1f} cm  |  {retreat_str}")
            ep_reward[:] = 0.0

            if current_ep >= num_episodes:
                # ── 汇总画面（5 秒）
                mean_r = float(np.mean(all_ep_returns))
                std_r = float(np.std(all_ep_returns))
                mean_pos = float(np.mean(all_ep_final_pos_cm))
                retreat_pct = sum(r > retreat_th for r in all_ep_retreat_ratios) / num_episodes * 100
                summary_lines = [
                    f"Mean Return: {mean_r:+.4f} +/- {std_r:.4f}",
                    f"Mean Final Pos: {mean_pos:.1f} cm",
                    f"Back-Retreat: {retreat_pct:.0f}% of episodes",
                    "IBVS 180-deg Singularity Test",
                ]
                for _ in range(int(args_cli.fps * 5)):
                    with torch.inference_mode():
                        outputs = runner.agent.act(obs, states, timestep=0, timesteps=0)
                        actions = outputs[-1].get("mean_actions", outputs[0])
                        obs, rewards, terminated, truncated, infos = env_skrl.step(actions)
                        states = env_skrl.state()
                    frame = render_viewport_frame(env)
                    if frame is not None:
                        frame = _put_text_right(frame, summary_lines, color=(0, 255, 255))
                        bottom = f"Mean Pos: {mean_pos:.1f}cm  Retreat: {retreat_pct:.0f}%"
                        font = cv2.FONT_HERSHEY_SIMPLEX
                        (tw, _), _ = cv2.getTextSize(bottom, font, 0.75, 2)
                        sx = (frame.shape[1] - tw) // 2
                        cv2.putText(frame, bottom, (sx+1, frame.shape[0]-29),
                                    font, 0.75, (0, 0, 0), 3, cv2.LINE_AA)
                        cv2.putText(frame, bottom, (sx, frame.shape[0]-30),
                                    font, 0.75, (0, 255, 255), 2, cv2.LINE_AA)
                        frames.append(frame)
                break

            current_ep += 1
            dist_history = []

            # 更新注释（含后退状态）
            color_code = (0, 64, 255) if retreat_flag else (0, 255, 0)  # 红/绿
            ann_lines = [
                f"Episode {current_ep}/{num_episodes}",
                "IBVS Singularity Test",
                "Joint7 += 180 deg",
                retreat_str,
            ]

            # 重置 + 注入奇异
            obs, _ = env_skrl.reset()
            states = env_skrl.state()
            _inject_singularity(base_env, scale=sing_scale)
            obs, states = _settle_after_inject(env_skrl, base_env, obs, states, settle_steps)

            # 新 episode 初始距离
            try:
                d0 = get_pos_error_m(base_env, hand_id)[0].item()
                initial_dist = d0
                dist_history.append(d0)
            except Exception:
                initial_dist = 0.0

        frame = render_viewport_frame(env)
        if frame is not None:
            frame = _put_text_right(frame, ann_lines, color=ann_color)
            frames.append(frame)

    env_skrl.close()

    # ── 最终汇总打印 ──────────────────────────────────────────────────────────
    if all_ep_returns:
        mean_r = float(np.mean(all_ep_returns))
        std_r = float(np.std(all_ep_returns))
        mean_pos = float(np.mean(all_ep_final_pos_cm))
        retreat_pct = sum(r > retreat_th for r in all_ep_retreat_ratios) / len(all_ep_retreat_ratios) * 100
        print(f"\n{'='*55}")
        print(f"  奇异点测试汇总 ({len(all_ep_returns)} episodes)")
        print(f"  Mean Return     : {mean_r:+.4f} +/- {std_r:.4f}")
        print(f"  Mean Final Pos  : {mean_pos:.2f} cm")
        print(f"  Back-Retreat    : {retreat_pct:.0f}% episodes "
              f"(threshold={retreat_th*100:.0f}%)")
        print(f"  Retreat ratios  : {[f'{r:.2f}' for r in all_ep_retreat_ratios]}")
        if retreat_pct > 50:
            print(f"  [!] 后退率 > 50%，建议加入 anti_retreat_vs 惩罚并重训")
        else:
            print(f"  [OK] 后退率 <= 50%，模型表现可接受")
        print(f"{'='*55}\n")

    # ── 写视频 ────────────────────────────────────────────────────────────────
    if not frames:
        print("[WARN] 无帧可写。")
        return

    tmp_raw = raw_mp4.replace(".mp4", "_tmp.mp4")
    write_video_from_frames(frames, tmp_raw, fps=args_cli.fps)
    if encode_h264(tmp_raw, raw_mp4):
        os.remove(tmp_raw)
    else:
        os.rename(tmp_raw, raw_mp4)

    # 尝试 ffmpeg drawtext 叠加黄色字（增强视觉效果）
    filter_str = (
        "drawtext=text='IBVS 180-deg Singularity Test | Joint7+=pi'"
        ":fontcolor=yellow:fontsize=26:x=w-tw-10:y=10"
        ":box=1:boxcolor=black@0.4:boxborderw=3"
    )
    ffmpeg_ok = subprocess.run(
        ["ffmpeg", "-y", "-i", raw_mp4, "-vf", filter_str,
         "-c:v", "libx264", "-crf", "20", final_mp4],
        capture_output=True, text=True
    ).returncode == 0

    if not ffmpeg_ok:
        import shutil
        shutil.copy2(raw_mp4, final_mp4)

    print(f"[INFO] 最终视频: {final_mp4}  ({len(frames)} 帧)")


if __name__ == "__main__":
    main()
    simulation_app.close()
