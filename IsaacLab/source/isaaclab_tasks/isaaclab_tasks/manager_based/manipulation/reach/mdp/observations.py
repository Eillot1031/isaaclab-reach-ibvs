# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

"""Custom observation functions for the reach task (visual servoing variant)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch

from isaaclab.assets import Articulation
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils.math import combine_frame_transforms, quat_apply, quat_rotate_inverse

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _project_to_image(
    pts_w: torch.Tensor,       # (N, P, 3)  world-frame 3D points
    cam_pos_w: torch.Tensor,   # (N, 3)     camera position in world
    cam_quat_w: torch.Tensor,  # (N, 4)     camera orientation in world (w, x, y, z)
    fx: float,
    fy: float,
    cx: float,
    cy: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Project N batches of P world-frame points into image coordinates.

    Returns:
        u: (N, P) pixel x coordinates
        v: (N, P) pixel y coordinates
    """
    N, P, _ = pts_w.shape

    # Translate to camera-centred world coordinates: (N, P, 3)
    pts_rel = pts_w - cam_pos_w.unsqueeze(1)

    # Rotate into camera frame via inverse rotation: (N*P, 3) → (N, P, 3)
    pts_cam = quat_rotate_inverse(
        cam_quat_w.unsqueeze(1).expand(-1, P, -1).reshape(N * P, 4),
        pts_rel.reshape(N * P, 3),
    ).reshape(N, P, 3)

    # Pinhole projection — clamp depth to avoid division by zero
    z = pts_cam[..., 2].clamp(min=1e-3)          # (N, P)
    u = fx * pts_cam[..., 0] / z + cx             # (N, P)
    v = fy * pts_cam[..., 1] / z + cy             # (N, P)
    return u, v


# ---------------------------------------------------------------------------
# Public observation function
# ---------------------------------------------------------------------------

def image_error_vs(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg,
    command_name: str,
    feature_half_size: float = 0.025,
    hand_eye_offset: tuple[float, float, float] = (0.0, 0.0, 0.107),
    fx: float = 500.0,
    fy: float = 500.0,
    cx: float = 320.0,
    cy: float = 240.0,
    img_w: float = 640.0,
    img_h: float = 480.0,
) -> torch.Tensor:
    """Compute an 8-D normalised image-error vector for image-based visual servoing.

    The function places 4 feature points at the corners of a square (side = 2 *
    feature_half_size) centred on and coplanar with the *target* end-effector pose,
    then projects them twice:

    1. Through the *current* EE camera → current pixel coordinates (u_i, v_i).
    2. Through the *desired* EE camera  → desired pixel coordinates (u_i*, v_i*).

    The error per point is ``e_i = [u_i − u_i*, v_i − v_i*]``.
    All four per-point errors are stacked and divided by image dimensions so the
    returned vector lies in a bounded range regardless of image resolution.

    The virtual camera is a pinhole model offset from ``panda_hand`` by
    ``hand_eye_offset`` (metres, in the EE body frame).  Its orientation is
    identical to the EE orientation (z-axis pointing forward out of the hand).

    Args:
        env:               The RL environment instance.
        asset_cfg:         Scene entity config identifying the robot; ``body_names``
                           must select ``panda_hand`` (or equivalent EE link).
        command_name:      Name of the ``ee_pose`` command term (body-frame 7-D
                           position + quaternion).
        feature_half_size: Half the side length of the square feature-point
                           pattern on the target board (metres).
        hand_eye_offset:   Translation of the virtual camera from the EE body
                           origin, expressed in the EE body frame (metres).
        fx, fy:            Camera focal lengths (pixels).
        cx, cy:            Camera principal point (pixels).
        img_w, img_h:      Image width and height used for normalisation.

    Returns:
        Tensor of shape ``(num_envs, 8)`` containing the normalised pixel errors
        ordered as ``[Δu₁/W, Δv₁/H, Δu₂/W, Δv₂/H, Δu₃/W, Δv₃/H, Δu₄/W, Δv₄/H]``.
    """
    asset: Articulation = env.scene[asset_cfg.name]
    command = env.command_manager.get_command(command_name)  # (N, 7): pos_b + quat_b

    N = command.shape[0]
    device = command.device

    # ---- Current EE pose (world frame) ------------------------------------
    ee_pos_w = asset.data.body_pos_w[:, asset_cfg.body_ids[0]]    # (N, 3)
    ee_quat_w = asset.data.body_quat_w[:, asset_cfg.body_ids[0]]  # (N, 4)

    # ---- Target EE pose (world frame) -------------------------------------
    des_pos_b = command[:, :3]
    des_quat_b = command[:, 3:7]
    des_pos_w, des_quat_w = combine_frame_transforms(
        asset.data.root_pos_w, asset.data.root_quat_w, des_pos_b, des_quat_b
    )  # (N, 3), (N, 4)

    # ---- Virtual camera poses (hand-eye offset applied) -------------------
    offset = torch.tensor(hand_eye_offset, dtype=torch.float32, device=device)
    offset_batch = offset.unsqueeze(0).expand(N, -1)  # (N, 3)

    cam_pos_w = ee_pos_w + quat_apply(ee_quat_w, offset_batch)   # (N, 3)
    cam_quat_w = ee_quat_w                                         # (N, 4)

    des_cam_pos_w = des_pos_w + quat_apply(des_quat_w, offset_batch)  # (N, 3)
    des_cam_quat_w = des_quat_w                                         # (N, 4)

    # ---- 4 feature points in target's local frame (z = 0 plane) ----------
    d = feature_half_size
    pts_local = torch.tensor(
        [[-d, -d, 0.0], [d, -d, 0.0], [-d, d, 0.0], [d, d, 0.0]],
        dtype=torch.float32,
        device=device,
    )  # (4, 3)

    # Transform feature points to world frame via TARGET pose
    # pts_w[n, p] = des_pos_w[n] + R(des_quat_w[n]) @ pts_local[p]
    pts_local_batch = pts_local.unsqueeze(0).expand(N, -1, -1)  # (N, 4, 3)
    pts_in_target_cam = quat_apply(
        des_quat_w.unsqueeze(1).expand(-1, 4, -1).reshape(N * 4, 4),
        pts_local_batch.reshape(N * 4, 3),
    ).reshape(N, 4, 3)                                           # (N, 4, 3)
    pts_w = des_pos_w.unsqueeze(1) + pts_in_target_cam          # (N, 4, 3)

    # ---- Project to current camera ----------------------------------------
    u_curr, v_curr = _project_to_image(pts_w, cam_pos_w, cam_quat_w, fx, fy, cx, cy)

    # ---- Project to desired camera ----------------------------------------
    u_des, v_des = _project_to_image(pts_w, des_cam_pos_w, des_cam_quat_w, fx, fy, cx, cy)

    # ---- Normalised pixel error --------------------------------------------
    # Interleave: [Δu1/W, Δv1/H, Δu2/W, Δv2/H, ...]
    err_u = (u_curr - u_des) / img_w   # (N, 4)
    err_v = (v_curr - v_des) / img_h   # (N, 4)

    err = torch.stack([err_u, err_v], dim=2).reshape(N, 8)  # (N, 4, 2) → (N, 8)
    return err
