"""Shared helpers for VS video recording, hold-at-goal, and command overrides."""

from __future__ import annotations

import os
import shutil
import subprocess

import cv2
import numpy as np
import torch

R37_EYE = (3.5, 3.5, 3.5)
R37_LOOKAT = (0.5, 0.0, 0.5)

CAMERA_PRESETS = {
    "perspective": {"eye": R37_EYE, "lookat": R37_LOOKAT},
    "top": {"eye": (0.5, 0.0, 4.0), "lookat": (0.5, 0.0, 0.0)},
    "side": {"eye": (3.5, 0.0, 1.5), "lookat": (0.5, 0.0, 0.5)},
    "front": {"eye": (0.5, 3.5, 1.5), "lookat": (0.5, 0.0, 0.5)},
}


def setup_r37_viewer(env_cfg, view: str = "perspective"):
    """Set viewer to R37-proven pose for RecordVideo / env.render()."""
    cam = CAMERA_PRESETS.get(view, CAMERA_PRESETS["perspective"])
    env_cfg.viewer.eye = cam["eye"]
    env_cfg.viewer.lookat = cam["lookat"]


def get_base_env(env):
    """Unwrap gym/skrl wrappers to reach the Isaac Lab base env."""
    base = env
    while hasattr(base, "env"):
        base = base.env
    if hasattr(base, "unwrapped"):
        base = base.unwrapped
    return base


def get_hand_body_id(base_env, body_name: str = "panda_hand") -> int | None:
    try:
        return base_env.scene["robot"].find_bodies(body_name)[0][0]
    except Exception:
        return None


def get_pos_error_m(base_env, hand_id: int | None = None) -> torch.Tensor | None:
    """Per-env EE→target distance in metres, shape (N,)."""
    if hand_id is None:
        hand_id = get_hand_body_id(base_env)
    if hand_id is None:
        return None
    try:
        from isaaclab.utils.math import combine_frame_transforms

        robot = base_env.scene["robot"]
        cmd = base_env.command_manager.get_command("ee_pose")
        des_pos_b = cmd[:, :3]
        des_pos_w, _ = combine_frame_transforms(
            robot.data.root_pos_w, robot.data.root_quat_w, des_pos_b
        )
        curr_pos_w = robot.data.body_pos_w[:, hand_id]
        return torch.norm(curr_pos_w - des_pos_w, dim=1)
    except Exception:
        return None


def image_error_start_index(obs_dim: int) -> int:
    if obs_dim >= 39:
        return 25
    if obs_dim >= 32:
        return 18
    return 0


def apply_hold_policy(
    actions: torch.Tensor,
    obs: torch.Tensor,
    base_env,
    *,
    pos_threshold_m: float = 0.025,
    image_threshold: float = 0.03,
    hand_id: int | None = None,
    enabled: bool = True,
) -> torch.Tensor:
    """Zero actions when Cartesian or image error is below threshold (hold at goal)."""
    if not enabled or (pos_threshold_m <= 0.0 and image_threshold <= 0.0):
        return actions

    freeze = torch.zeros(actions.shape[0], 1, device=actions.device)
    pos_err = get_pos_error_m(base_env, hand_id)
    if pos_err is not None and pos_threshold_m > 0.0:
        freeze = torch.maximum(freeze, (pos_err.unsqueeze(-1) < pos_threshold_m).float())

    if image_threshold > 0.0:
        if obs.shape[1] < 32:
            if not getattr(apply_hold_policy, "_warned_no_image_obs", False):
                print(
                    "[WARN] image hold skipped: obs dim < 32 (no image_error); "
                    "use --hold_image_threshold 0 for IK-Rel.",
                    flush=True,
                )
                apply_hold_policy._warned_no_image_obs = True
        else:
            ie_start = image_error_start_index(obs.shape[1])
            img_err_norm = torch.norm(obs[:, ie_start : ie_start + 8], dim=1, keepdim=True)
            freeze = torch.maximum(freeze, (img_err_norm < image_threshold).float())

    return actions * (1.0 - freeze)


def write_target_pose_world(base_env, x: float, y: float, z: float):
    """Write moving target into pose_command_b (body frame) so policy obs updates."""
    from isaaclab.utils.math import subtract_frame_transforms

    cmd_mgr = base_env.command_manager
    terms = getattr(cmd_mgr, "_terms", None) or getattr(cmd_mgr, "terms", {})
    term = terms.get("ee_pose", None)
    if term is None:
        return

    robot = base_env.scene["robot"]
    N = base_env.num_envs
    dev = robot.data.root_pos_w.device

    target_w = torch.tensor([[x, y, z]], device=dev, dtype=torch.float32).expand(N, -1)
    target_quat_w = term.pose_command_w[:, 3:7].clone()

    root_pos = robot.data.root_pos_w
    root_quat = robot.data.root_quat_w
    pos_b, quat_b = subtract_frame_transforms(root_pos, root_quat, target_w, target_quat_w)

    term.pose_command_b[:, :3] = pos_b
    term.pose_command_b[:, 3:7] = quat_b

    if hasattr(term, "_update_metrics"):
        term._update_metrics()


def render_viewport_frame(env) -> np.ndarray | None:
    """Grab main viewport RGB from env.render() (includes debug_vis markers)."""
    frame = env.render()
    if frame is None:
        return None
    arr = np.asarray(frame, dtype=np.uint8)
    if arr.ndim == 3 and arr.shape[-1] == 4:
        arr = arr[..., :3]
    # OpenCV putText requires contiguous HxWx3 uint8 (env.render may return a view).
    return np.ascontiguousarray(arr)


def grab_wrist_frame(base_env, env_idx: int = 0) -> np.ndarray | None:
    """Grab wrist TiledCamera RGB frame."""
    try:
        cam = base_env.scene["wrist_cam"]
        rgb = cam.data.output["rgb"]
        if rgb is None or rgb.numel() == 0:
            return None
        frame = rgb[env_idx].cpu().numpy()
        if frame.shape[-1] == 4:
            frame = frame[..., :3]
        if frame.dtype in (np.float32, np.float64):
            if frame.max() <= 1.0 + 1e-3:
                frame = (frame * 255.0).clip(0, 255)
            else:
                frame = frame.clip(0, 255)
        return frame.astype(np.uint8)
    except Exception:
        return None


def write_video_from_frames(frames: list, path: str, fps: float = 30.0):
    if not frames:
        print(f"[WARN] No frames to write for {path}")
        return
    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    for f in frames:
        writer.write(cv2.cvtColor(f, cv2.COLOR_RGB2BGR))
    writer.release()
    print(f"[INFO] Saved video: {path}  ({len(frames)} frames @ {fps:.0f} fps)")


def finalize_recordvideo_main(video_folder: str, name_prefix: str, out_mp4: str) -> bool:
    """Rename gym RecordVideo output (prefix-step-0.mp4) to out_mp4."""
    src = os.path.join(video_folder, f"{name_prefix}-step-0.mp4")
    if not os.path.isfile(src):
        candidates = [
            os.path.join(video_folder, f)
            for f in os.listdir(video_folder)
            if f.endswith(".mp4") and name_prefix in f
        ]
        if not candidates:
            print(f"[WARN] RecordVideo output not found in {video_folder}")
            return False
        src = candidates[0]
    shutil.copy2(src, out_mp4)
    print(f"[INFO] Main viewport video: {out_mp4}")
    return True


def make_composite(persp_mp4: str, wrist_mp4: str, out_mp4: str, height: int = 720):
    cmd = [
        "ffmpeg", "-y",
        "-i", persp_mp4,
        "-i", wrist_mp4,
        "-filter_complex",
        f"[0:v]scale=-2:{height}[main];[1:v]scale=-2:{height}[wrist];[main][wrist]hstack=inputs=2[out]",
        "-map", "[out]",
        "-c:v", "libx264", "-crf", "20",
        out_mp4,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[INFO] Composite video saved: {out_mp4}")
    else:
        print(f"[WARN] ffmpeg composite failed:\n{result.stderr[-800:]}")


def encode_h264(raw_mp4: str, out_mp4: str) -> bool:
    cmd = ["ffmpeg", "-y", "-i", raw_mp4, "-c:v", "libx264", "-crf", "20", out_mp4]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return True
    print(f"[WARN] ffmpeg encode failed:\n{result.stderr[-400:]}")
    return False


def print_checkpoint_summary(checkpoint_path: str):
    """Run verify_vs6_checkpoint and print one-line summary."""
    try:
        from verify_vs6_checkpoint import verify_vs6_checkpoint, print_summary

        info = verify_vs6_checkpoint(checkpoint_path, strict=False)
        print_summary(info)
    except Exception as e:
        print(f"[WARN] Checkpoint verification skipped: {e}")
