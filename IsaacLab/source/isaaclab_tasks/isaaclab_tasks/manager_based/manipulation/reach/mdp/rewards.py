# Copyright (c) 2022-2026, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from typing import TYPE_CHECKING

import torch

from isaaclab.assets import Articulation, RigidObject
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils.math import combine_frame_transforms, quat_error_magnitude, quat_mul

from .observations import image_error_vs

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


def position_command_error(env: ManagerBasedRLEnv, command_name: str, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    """Penalize tracking of the position error using L2-norm.

    The function computes the position error between the desired position (from the command) and the
    current position of the asset's body (in world frame). The position error is computed as the L2-norm
    of the difference between the desired and current positions.
    """
    # extract the asset (to enable type hinting)
    asset: RigidObject = env.scene[asset_cfg.name]
    command = env.command_manager.get_command(command_name)
    # obtain the desired and current positions
    des_pos_b = command[:, :3]
    des_pos_w, _ = combine_frame_transforms(asset.data.root_pos_w, asset.data.root_quat_w, des_pos_b)
    curr_pos_w = asset.data.body_pos_w[:, asset_cfg.body_ids[0]]  # type: ignore
    return torch.norm(curr_pos_w - des_pos_w, dim=1)


def position_command_error_tanh(
    env: ManagerBasedRLEnv, std: float, command_name: str, asset_cfg: SceneEntityCfg
) -> torch.Tensor:
    """Reward tracking of the position using the tanh kernel.

    The function computes the position error between the desired position (from the command) and the
    current position of the asset's body (in world frame) and maps it with a tanh kernel.
    """
    # extract the asset (to enable type hinting)
    asset: RigidObject = env.scene[asset_cfg.name]
    command = env.command_manager.get_command(command_name)
    # obtain the desired and current positions
    des_pos_b = command[:, :3]
    des_pos_w, _ = combine_frame_transforms(asset.data.root_pos_w, asset.data.root_quat_w, des_pos_b)
    curr_pos_w = asset.data.body_pos_w[:, asset_cfg.body_ids[0]]  # type: ignore
    distance = torch.norm(curr_pos_w - des_pos_w, dim=1)
    return 1 - torch.tanh(distance / std)


def orientation_command_error(env: ManagerBasedRLEnv, command_name: str, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    """Penalize tracking orientation error using shortest path.

    The function computes the orientation error between the desired orientation (from the command) and the
    current orientation of the asset's body (in world frame). The orientation error is computed as the shortest
    path between the desired and current orientations.
    """
    # extract the asset (to enable type hinting)
    asset: RigidObject = env.scene[asset_cfg.name]
    command = env.command_manager.get_command(command_name)
    # obtain the desired and current orientations
    des_quat_b = command[:, 3:7]
    des_quat_w = quat_mul(asset.data.root_quat_w, des_quat_b)
    curr_quat_w = asset.data.body_quat_w[:, asset_cfg.body_ids[0]]  # type: ignore
    return quat_error_magnitude(curr_quat_w, des_quat_w)


def reach_success_bonus(
    env: ManagerBasedRLEnv,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    pos_threshold: float = 0.03,
    angle_threshold: float = 0.175,
) -> torch.Tensor:
    """Sparse +1 bonus when EE is within pos_threshold (m) and angle_threshold (rad) simultaneously.

    Provides a clear success signal for the policy to optimize toward precise reaching.
    pos_threshold=0.03 means 3 cm; angle_threshold=0.175 rad means ~10 degrees.
    """
    asset: RigidObject = env.scene[asset_cfg.name]
    command = env.command_manager.get_command(command_name)
    # position error
    des_pos_b = command[:, :3]
    des_pos_w, _ = combine_frame_transforms(asset.data.root_pos_w, asset.data.root_quat_w, des_pos_b)
    curr_pos_w = asset.data.body_pos_w[:, asset_cfg.body_ids[0]]  # type: ignore
    pos_error = torch.norm(curr_pos_w - des_pos_w, dim=1)
    # orientation error
    des_quat_b = command[:, 3:7]
    des_quat_w = quat_mul(asset.data.root_quat_w, des_quat_b)
    curr_quat_w = asset.data.body_quat_w[:, asset_cfg.body_ids[0]]  # type: ignore
    angle_error = quat_error_magnitude(curr_quat_w, des_quat_w)
    return ((pos_error < pos_threshold) & (angle_error < angle_threshold)).float()


# ---------------------------------------------------------------------------
# Visual Servoing reward terms (paper Li et al. 2025, Section 3.4.3)
# ---------------------------------------------------------------------------

def image_error_improvement_vs(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg,
    command_name: str,
    lambda1: float = 2.0,
    eps: float = 1e-6,
) -> torch.Tensor:
    """Dense reward r_d1 from the paper: normalised relative improvement of image error.

    r = -lambda1 * (||e_t|| - ||e_{t-1}||) / ||e_{t-1}||

    The cache ``_vs_prev_enorm`` is reset per-environment whenever that env's
    episode terminates, preventing the large negative spike that would otherwise
    occur on the first step of a new episode (when norm jumps from ~0 back to
    the initial large value).
    """
    e_t = image_error_vs(env, asset_cfg=asset_cfg, command_name=command_name)
    norm_t = torch.norm(e_t, dim=1)  # (N,)

    cache_key = "_vs_prev_enorm"

    # Initialise cache on very first call
    if not hasattr(env, cache_key):
        setattr(env, cache_key, norm_t.detach().clone())

    prev_norm: torch.Tensor = getattr(env, cache_key)

    # Re-initialise if batch size changed
    if prev_norm.shape != norm_t.shape:
        prev_norm = norm_t.detach().clone()

    # Reset prev_norm for envs whose episode just terminated, so the first
    # step of the new episode computes reward = 0 rather than a huge spike.
    # Isaac Lab stores the termination flags in termination_manager.dones (bool, shape N).
    done_mask = None
    if hasattr(env, "termination_manager"):
        try:
            done_mask = env.termination_manager.dones  # (N,) bool
        except Exception:
            pass
    if done_mask is not None:
        prev_norm = prev_norm.clone()
        prev_norm[done_mask] = norm_t[done_mask].detach()

    reward = -lambda1 * (norm_t - prev_norm) / (prev_norm + eps)
    setattr(env, cache_key, norm_t.detach().clone())
    return reward


def image_error_success_vs(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg,
    command_name: str,
    delta: float = 0.02,
) -> torch.Tensor:
    """Sparse +1 reward when the normalised image-error L2 norm drops below delta.

    delta=0.02 corresponds to the feature points being within ~13px of their
    desired positions across all 4 points in a 640x480 image.
    """
    e_t = image_error_vs(env, asset_cfg=asset_cfg, command_name=command_name)
    return (torch.norm(e_t, dim=1) <= delta).float()
