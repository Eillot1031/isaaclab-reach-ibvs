#!/usr/bin/env python3
"""
Annotated play script: records 10-episode evaluation video with on-screen overlays.

Overlays added via ffmpeg post-processing:
  - Top-right: cumulative return for each episode, shown for 3s after episode ends
  - Bottom: 10-episode Mean Return, shown for 5s after all episodes complete

Usage (from IsaacLab directory):
    cd /home/krz/isaaclab_ws/IsaacLab
    OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
        ../scripts/play_view_annotated.py \
        --task Isaac-Reach-Franka-IK-Rel-Play-v0 \
        --headless --num_envs 4 --algorithm SAC \
        --num_episodes 10 \
        --label "A0: Full Model" \
        --checkpoint <path/to/best_agent.pt> \
        --out_video <path/to/output.mp4>
"""

"""Launch Isaac Sim first."""

import argparse
import sys

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Annotated play for SKRL SAC.")
parser.add_argument("--num_episodes", type=int, default=10)
parser.add_argument("--num_envs",     type=int, default=4)
parser.add_argument("--task",         type=str, default="Isaac-Reach-Franka-IK-Rel-Play-v0")
parser.add_argument("--algorithm",    type=str, default="SAC")
parser.add_argument("--checkpoint",   type=str, required=True)
parser.add_argument("--seed",         type=int, default=42)
parser.add_argument("--view",         type=str, default="perspective",
                    choices=["perspective", "top", "side", "front"])
parser.add_argument("--label",        type=str, default="",
                    help="Model label shown in video (e.g. 'A0: Full Model')")
parser.add_argument("--out_video",    type=str, default=None,
                    help="Path for the final annotated video. "
                         "Defaults to <checkpoint_dir>/videos/annotated_eval.mp4")
parser.add_argument("--ml_framework", type=str, default="torch")
AppLauncher.add_app_launcher_args(parser)

args_cli, hydra_args = parser.parse_known_args()
args_cli.enable_cameras = True
sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import os, json, statistics, subprocess, shutil, tempfile
import gymnasium as gym
import torch
import skrl
from packaging import version
from skrl.utils.runner.torch import Runner
from isaaclab.envs import ManagerBasedRLEnvCfg, DirectRLEnvCfg, DirectMARLEnvCfg
from isaaclab.utils.dict import print_dict
from isaaclab_rl.skrl import SkrlVecEnvWrapper
import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils import get_checkpoint_path
from isaaclab_tasks.utils.hydra import hydra_task_config

SKRL_VERSION = "2.0.0"
if version.parse(skrl.__version__) < version.parse(SKRL_VERSION):
    skrl.logger.error(f"Unsupported skrl version: {skrl.__version__}"); exit()

CAMERA_PRESETS = {
    "perspective": {"eye": (3.5, 3.5, 3.5), "lookat": (0.5, 0.0, 0.5)},
    "top":         {"eye": (0.5, 0.0, 4.0),  "lookat": (0.5, 0.0, 0.0)},
    "side":        {"eye": (3.5, 0.0, 1.5),  "lookat": (0.5, 0.0, 0.5)},
    "front":       {"eye": (0.5, 3.5, 1.5),  "lookat": (0.5, 0.0, 0.5)},
}

algorithm = args_cli.algorithm.lower()
agent_cfg_entry_point = "skrl_cfg_entry_point" if algorithm == "ppo" else f"skrl_{algorithm}_cfg_entry_point"


def _steps_per_episode(env_cfg) -> int:
    return int(env_cfg.episode_length_s / (env_cfg.sim.dt * env_cfg.decimation))


def get_video_fps(video_path: str) -> float:
    """Use ffprobe to get video FPS."""
    cmd = [
        "ffprobe", "-v", "quiet", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    rate_str = result.stdout.strip()
    if "/" in rate_str:
        num, den = rate_str.split("/")
        return float(num) / float(den)
    return float(rate_str) if rate_str else 30.0


def annotate_video(raw_video: str, out_video: str, episode_data: list[dict],
                   mean_ret: float, std_ret: float, label: str):
    """
    Post-process raw_video with ffmpeg drawtext to add:
      - Per-episode return in top-right (shown for 3s after each episode end)
      - Mean return at bottom (shown for 5s after all episodes, with freeze)
    """
    fps = get_video_fps(raw_video)
    print(f"[ANNOTATE] Video FPS: {fps:.2f}")

    # Build drawtext filter chains
    filters = []

    # 1) Label (model name) always visible top-left
    if label:
        safe_label = label.replace("'", "\\'").replace(":", "\\:")
        filters.append(
            f"drawtext=text='{safe_label}'"
            f":fontsize=28:fontcolor=white:borderw=2:bordercolor=black"
            f":x=20:y=20"
        )

    # 2) Per-episode return — top-right, shown 3s after episode ends.
    #    Episodes ending at the same step are stacked vertically.
    display_duration = 3.0
    fontsize_ep = 24
    line_height = fontsize_ep + 6  # pixels between lines

    # Group episodes by end_step
    from collections import defaultdict
    step_groups: dict = defaultdict(list)
    for ep in episode_data:
        step_groups[ep["end_step"]].append(ep)

    for end_step, eps in step_groups.items():
        t_start = end_step / fps
        t_end   = t_start + display_duration
        for row_idx, ep in enumerate(eps):
            ep_num = ep["episode"]
            ep_ret = ep["return"]
            sign   = "+" if ep_ret >= 0 else ""
            text   = f"Ep {ep_num:2d}  Return\\: {sign}{ep_ret:.3f}"
            y_pos  = 20 + row_idx * line_height
            filters.append(
                f"drawtext=text='{text}'"
                f":fontsize={fontsize_ep}:fontcolor=yellow:borderw=2:bordercolor=black"
                f":x=(w-text_w-20):y={y_pos}"
                f":enable='between(t,{t_start:.3f},{t_end:.3f})'"
            )

    # 3) Freeze last frame for 5s and show Mean Return at bottom
    freeze_dur = 5.0
    total_dur  = sum(1 for _ in open(raw_video, "rb")) / fps if False else None  # placeholder
    # Use ffprobe for total duration
    cmd_dur = [
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", raw_video
    ]
    dur_str = subprocess.run(cmd_dur, capture_output=True, text=True).stdout.strip()
    total_dur = float(dur_str) if dur_str else (episode_data[-1]["end_step"] / fps)
    print(f"[ANNOTATE] Raw video duration: {total_dur:.2f}s")

    sign_m = "+" if mean_ret >= 0 else ""
    mean_text = f"10-Episode Mean Return\\: {sign_m}{mean_ret:.4f}  Std\\: ±{std_ret:.4f}"
    summary_t_start = total_dur
    summary_t_end   = total_dur + freeze_dur

    filters.append(
        f"drawtext=text='{mean_text}'"
        f":fontsize=30:fontcolor=white:borderw=3:bordercolor=black"
        f":x=(w-text_w)/2:y=(h-text_h-30)"
        f":enable='gte(t,{summary_t_start:.3f})'"
    )

    filter_str = ",".join(filters)

    # Build ffmpeg command: freeze last frame + drawtext
    os.makedirs(os.path.dirname(os.path.abspath(out_video)), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", raw_video,
        "-vf", f"tpad=stop_mode=clone:stop_duration={freeze_dur},{filter_str}",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        out_video
    ]
    print(f"[ANNOTATE] Running ffmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ANNOTATE] ffmpeg stderr:\n{result.stderr[-2000:]}")
        raise RuntimeError("ffmpeg annotation failed")
    print(f"[ANNOTATE] Saved annotated video: {out_video}")


@hydra_task_config(args_cli.task, agent_cfg_entry_point)
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, experiment_cfg: dict):
    cam = CAMERA_PRESETS[args_cli.view]
    env_cfg.viewer.eye    = cam["eye"]
    env_cfg.viewer.lookat = cam["lookat"]
    env_cfg.scene.num_envs = args_cli.num_envs
    experiment_cfg["seed"] = args_cli.seed
    env_cfg.seed           = args_cli.seed

    steps_per_ep     = _steps_per_episode(env_cfg)
    num_episodes     = args_cli.num_episodes
    total_video_steps = num_episodes * steps_per_ep
    print(f"[INFO] Steps/ep: {steps_per_ep} | Episodes: {num_episodes} | Total steps: {total_video_steps}")

    resume_path = os.path.abspath(args_cli.checkpoint)
    log_dir     = os.path.dirname(os.path.dirname(resume_path))

    # Determine output paths
    raw_video_dir = os.path.join(log_dir, "videos", "annotated_raw")
    os.makedirs(raw_video_dir, exist_ok=True)

    if args_cli.out_video:
        out_video = os.path.abspath(args_cli.out_video)
    else:
        out_video = os.path.join(log_dir, "videos", "annotated_eval.mp4")

    env_cfg.log_dir = log_dir
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array")
    env = gym.wrappers.RecordVideo(
        env,
        video_folder=raw_video_dir,
        name_prefix="raw",
        step_trigger=lambda step: step == 0,
        video_length=total_video_steps,
        disable_logger=True,
    )
    env_skrl = SkrlVecEnvWrapper(env, ml_framework=args_cli.ml_framework)

    experiment_cfg["trainer"]["close_environment_at_exit"] = False
    experiment_cfg["agent"]["experiment"]["write_interval"]     = 0
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

    print(f"[INFO] Loading checkpoint: {resume_path}")
    runner.agent.load(resume_path)
    runner.agent.enable_training_mode(False, apply_to_models=True)

    obs, _    = env_skrl.reset()
    states    = env_skrl.state()
    n_envs    = env_cfg.scene.num_envs
    ep_rewards     = torch.zeros(n_envs, device=obs.device)
    ep_counts      = torch.zeros(n_envs, dtype=torch.long, device=obs.device)
    all_returns    = []
    episode_data   = []   # {episode, return, end_step}
    timestep       = 0

    print(f"\n{'='*60}\n  Annotated Evaluation: {num_episodes} episodes\n{'='*60}")

    while simulation_app.is_running():
        with torch.inference_mode():
            outputs = runner.agent.act(obs, states, timestep=0, timesteps=0)
            actions = outputs[-1].get("mean_actions", outputs[0])
            obs, rewards, terminated, truncated, infos = env_skrl.step(actions)
            states  = env_skrl.state()

        ep_rewards += rewards.squeeze(-1) if rewards.dim() > 1 else rewards
        timestep   += 1

        dones = (terminated | truncated).squeeze(-1) if terminated.dim() > 1 else (terminated | truncated)
        for idx in dones.nonzero(as_tuple=False).squeeze(-1):
            i      = idx.item()
            ep_ret = ep_rewards[i].item()
            ep_counts[i] += 1
            all_returns.append(ep_ret)
            global_ep = len(all_returns)
            episode_data.append({"episode": global_ep, "return": ep_ret, "end_step": timestep})
            ep_rewards[i] = 0.0
            print(f"  Episode {global_ep:3d} (env {i}) | Return: {ep_ret:+.4f}  [step {timestep}]")

        if len(all_returns) >= num_episodes:
            # Finish current episode to complete the video
            remaining = steps_per_ep - (timestep % steps_per_ep)
            if remaining < steps_per_ep:
                for _ in range(remaining):
                    with torch.inference_mode():
                        outputs = runner.agent.act(obs, states, timestep=0, timesteps=0)
                        actions = outputs[-1].get("mean_actions", outputs[0])
                        obs, rewards, terminated, truncated, infos = env_skrl.step(actions)
                        states = env_skrl.state()
                    timestep += 1
            break

        if timestep >= total_video_steps:
            break

    returns  = all_returns[:num_episodes]
    mean_ret = statistics.mean(returns)
    std_ret  = statistics.stdev(returns) if len(returns) > 1 else 0.0
    print(f"\n{'='*60}")
    print(f"  Mean Return : {mean_ret:+.4f} +/- {std_ret:.4f}")
    print(f"{'='*60}\n")

    env_skrl.close()

    # Find the raw video file
    raw_mp4 = os.path.join(raw_video_dir, "raw-step-0.mp4")
    if not os.path.exists(raw_mp4):
        candidates = [f for f in os.listdir(raw_video_dir) if f.endswith(".mp4")]
        if candidates:
            raw_mp4 = os.path.join(raw_video_dir, sorted(candidates)[-1])
    if not os.path.exists(raw_mp4):
        print(f"[WARN] Raw video not found in {raw_video_dir}; skipping annotation.")
    else:
        annotate_video(
            raw_video=raw_mp4,
            out_video=out_video,
            episode_data=episode_data[:num_episodes],
            mean_ret=mean_ret,
            std_ret=std_ret,
            label=args_cli.label,
        )

    # Save summary JSON next to output video
    summary = {
        "label":      args_cli.label,
        "checkpoint": resume_path,
        "num_episodes": len(returns),
        "mean_return": mean_ret,
        "std_return":  std_ret,
        "episodes":   episode_data[:num_episodes],
    }
    json_path = out_video.replace(".mp4", "_summary.json")
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"[INFO] Summary saved: {json_path}")


if __name__ == "__main__":
    main()
    simulation_app.close()
