# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

"""Visual Servoing (VS) variant of the Franka reach environment.

Observation space (34D):
    generated_commands (6D) | image_error (8D) | joint_pos_rel (7D) | joint_vel_rel (7D) | last_action (6D)

Both Cartesian pose commands AND image-space error are included.
``generated_commands`` provides the 3-D direction to the target (needed since
``image_error`` alone has depth ambiguity and cannot guide the policy to the
correct 3-D position). ``image_error`` provides singularity-aware guidance
and can steer around IBVS 180-degree configurations.

Action space: identical to IK-Rel (6D relative EE pose increments).
"""

from __future__ import annotations

import numpy as np
import isaaclab.sim as sim_utils
from isaaclab.managers import ObservationGroupCfg as ObsGroup
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.sensors import CameraCfg, TiledCameraCfg
from isaaclab.utils import configclass
from isaaclab.utils.noise import AdditiveUniformNoiseCfg as Unoise

import isaaclab_tasks.manager_based.manipulation.reach.mdp as mdp

from . import ik_rel_env_cfg


##
# Camera helpers
##

def _lookat_quat_world(eye, target, world_up=(0.0, 0.0, 1.0)):
    """Compute a wxyz quaternion for a camera in 'world' convention looking from eye to target.

    In Isaac Lab 'world' convention: camera forward axis = local +X, up axis = local +Z.
    Returns tuple (w, x, y, z).
    """
    eye = np.asarray(eye, dtype=float)
    target = np.asarray(target, dtype=float)
    world_up = np.asarray(world_up, dtype=float)

    fwd = target - eye
    fwd /= np.linalg.norm(fwd)

    cam_y = np.cross(world_up, fwd)
    if np.linalg.norm(cam_y) < 1e-6:
        cam_y = np.array([0.0, 1.0, 0.0])
    else:
        cam_y /= np.linalg.norm(cam_y)

    cam_z = np.cross(fwd, cam_y)
    cam_z /= np.linalg.norm(cam_z)

    # Rotation matrix: columns = camera's X(fwd), Y(cam_y), Z(cam_z) in world frame
    R = np.column_stack([fwd, cam_y, cam_z])
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = np.sqrt(1.0 + tr) * 2.0
        w = s / 4.0
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        w = (R[2, 1] - R[1, 2]) / s
        x = s / 4.0
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = s / 4.0
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = s / 4.0
    norm = np.sqrt(w*w + x*x + y*y + z*z)
    return (w/norm, x/norm, y/norm, z/norm)


# Perspective camera: R37-proven viewer pose eye=(3.5,3.5,3.5) -> lookat=(0.5,0,0.5)
_PERSP_QUAT = tuple(float(v) for v in _lookat_quat_world(eye=(3.5, 3.5, 3.5), target=(0.5, 0.0, 0.5)))


##
# VS Policy observation group — defined at module level for reliability
##

@configclass
class _VSPolicyCfg(ObsGroup):
    """VS policy observations (34D total).

    Layout: generated_commands (6D) | image_error (8D) | joint_pos_rel (7D) | joint_vel_rel (7D) | last_action (6D)

    generated_commands provides the Cartesian 3-D direction to the target, which is
    critical for convergence since image_error alone has depth ambiguity.
    image_error provides singularity-aware guidance for fine-tuning and IBVS behaviour.
    """

    pose_command = ObsTerm(func=mdp.generated_commands, params={"command_name": "ee_pose"})
    joint_pos = ObsTerm(func=mdp.joint_pos_rel, noise=Unoise(n_min=-0.01, n_max=0.01))
    joint_vel = ObsTerm(func=mdp.joint_vel_rel, noise=Unoise(n_min=-0.01, n_max=0.01))
    image_error = ObsTerm(
        func=mdp.image_error_vs,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=["panda_hand"]),
            "command_name": "ee_pose",
            "feature_half_size": 0.025,
            "hand_eye_offset": (0.0, 0.0, 0.107),
            "fx": 500.0,
            "fy": 500.0,
            "cx": 320.0,
            "cy": 240.0,
            "img_w": 640.0,
            "img_h": 480.0,
        },
    )
    actions = ObsTerm(func=mdp.last_action)

    def __post_init__(self):
        self.enable_corruption = True
        self.concatenate_terms = True


##
# Environment configurations
##

@configclass
class FrankaReachEnvCfg_VS(ik_rel_env_cfg.FrankaReachEnvCfg):
    """Franka reach env with visual-servoing observation space.

    Inherits the IK-Rel action space and all reward / termination terms.
    The policy observation group is overridden to use ``image_error_vs``
    instead of ``generated_commands``.
    """

    def __post_init__(self):
        super().__post_init__()

        # Replace the base PolicyCfg with the VS one (removes pose_command,
        # adds image_error — derived from geometric pinhole projection).
        self.observations.policy = _VSPolicyCfg()

        # Disable debug visualization to avoid loading remote marker USD files
        self.commands.ee_pose.debug_vis = False

        # ------------------------------------------------------------------
        # Override reward terms to align with image-space observation.
        #
        # Paper (Li et al. 2025, Sec 3.4.3):
        #   r_d1  = -λ1*(‖e_t‖ - ‖e_{t-1}‖) / ‖e_{t-1}‖  (normalised improvement)
        #   r_d2  = -λ2*<a,a>       → joint_vel (existing)
        #   r_d3  = -λ3*‖a_t-a_{t-1}‖  → action_rate (existing)
        #   r_s   = sparse success / fail signal
        #
        # We ADD image_error_improvement alongside position_tracking_fine_grained
        # so the policy gets both 3-D Cartesian guidance AND image-space gradient.
        # ------------------------------------------------------------------
        _asset = SceneEntityCfg("robot", body_names=["panda_hand"])

        # VS v6: add generated_commands (Cartesian pose error) back to observation.
        # v4/v5 failure: image_error alone has depth ambiguity — the policy can
        # reduce pixel error without converging in 3D space, producing positive
        # rewards with 45cm+ position errors. Fix: include generated_commands
        # alongside image_error so the policy has unambiguous 3D direction info.
        # Rewards: strong Cartesian L2 as primary, image-space as supplementary.
        # - end_effector_position_tracking (L2) = -0.2: main convergence signal
        # - image_error_improvement weight=0.5: supplementary VS guidance
        # - image_error_success weight=1.0, delta=0.1: VS success bonus
        self.rewards.end_effector_position_tracking.weight = -0.2

        self.rewards.image_error_improvement = RewTerm(
            func=mdp.image_error_improvement_vs,
            weight=0.5,
            params={
                "asset_cfg": _asset,
                "command_name": "ee_pose",
                "lambda1": 1.0,
            },
        )

        self.rewards.image_error_success = RewTerm(
            func=mdp.image_error_success_vs,
            weight=1.0,
            params={
                "asset_cfg": _asset,
                "command_name": "ee_pose",
                "delta": 0.1,
            },
        )


@configclass
class FrankaReachEnvCfg_VS_v7(FrankaReachEnvCfg_VS):
    """VS v7: image_error in observations only — no image-space rewards.

    VS v6 diagnosis: ``image_error_improvement`` (weight=0.5) fought against
    the Cartesian position-tracking reward, causing unstable convergence
    (image_error_success=0 throughout training; mean final pos error ~20 cm
    after fixing the evaluation-script bug).

    VS v7 fix: remove all image-space reward terms.  The policy still receives
    ``image_error`` (8D) in its observation, giving it VS information to exploit,
    but is rewarded purely on 3-D Cartesian and orientation precision.
    This lets the Cartesian rewards drive clean convergence without interference.
    """

    def __post_init__(self):
        super().__post_init__()

        # Remove image-space reward terms that conflict with Cartesian tracking
        if hasattr(self.rewards, "image_error_improvement"):
            del self.rewards.image_error_improvement
        if hasattr(self.rewards, "image_error_success"):
            del self.rewards.image_error_success

        # Restore fine-grained position tracking that was not explicitly set in v6
        # (inherited from IK-Rel: end_effector_position_tracking_fine_grained w=0.5)


@configclass
class FrankaReachEnvCfg_VS_v7_PLAY(FrankaReachEnvCfg_VS_v7):
    """Play / evaluation variant for VS v7."""

    def __post_init__(self):
        super().__post_init__()

        self.scene.num_envs = 50
        self.scene.env_spacing = 2.5
        self.observations.policy.enable_corruption = False

        # Disable command resampling so target stays fixed for the full episode
        self.commands.ee_pose.resampling_time_range = (1e9, 1e9)

        # No TiledCamera added — see FrankaReachEnvCfg_VS_PLAY docstring for rationale.


@configclass
class FrankaReachEnvCfg_VS_PLAY(FrankaReachEnvCfg_VS):
    """Play / evaluation variant: smaller scene, no noise.

    No TiledCamera is added here — the main viewport (env.render()) works
    correctly without TiledCamera in headless mode.  Adding a TiledCamera
    to the scene causes env.render() to return gray frames.
    Wrist/perspective video is handled in scripts via viewer + manual env.render()
    (see VS_Record_PLAY; do not use gym RecordVideo when wrist_cam is in the scene).
    """

    def __post_init__(self):
        super().__post_init__()

        # Smaller scene for interactive play
        self.scene.num_envs = 50
        self.scene.env_spacing = 2.5

        # Disable observation noise during evaluation
        self.observations.policy.enable_corruption = False

        # Disable command resampling during evaluation so the target stays fixed
        # for the full episode.  The base config uses (12.0, 12.0) which matches
        # episode_length_s=12.0 exactly — the command can be resampled on the very
        # last step, corrupting any post-step position-error measurement.
        self.commands.ee_pose.resampling_time_range = (1e9, 1e9)


# Wrist camera: ROS convention, look forward-down (from stack visuomotor config).
_WRIST_QUAT_ROS = (-0.70614, 0.03701, 0.03701, -0.70614)


@configclass
class FrankaReachEnvCfg_VS_Record_PLAY(FrankaReachEnvCfg_VS_PLAY):
    """Play variant for video recording: manual env.render() viewport + wrist TiledCamera.

    Do not wrap with gym RecordVideo while wrist_cam is present — viewport capture goes gray.
    Scripts call render_viewport_frame() each step (same path as play_tracking_demo).
    """

    def __post_init__(self):
        super().__post_init__()

        # Goal/EE coordinate frames in viewport (R37-style); only for recording, not eval speed.
        self.commands.ee_pose.debug_vis = True

        self.num_rerenders_on_reset = 3

        self.scene.wrist_cam = TiledCameraCfg(
            prim_path="{ENV_REGEX_NS}/Robot/panda_hand/wrist_cam",
            update_period=0.0,
            height=480,
            width=640,
            data_types=["rgb"],
            spawn=sim_utils.PinholeCameraCfg(
                focal_length=24.0,
                focus_distance=400.0,
                horizontal_aperture=20.955,
                clipping_range=(0.05, 5.0),
            ),
            offset=TiledCameraCfg.OffsetCfg(
                pos=(0.0, 0.0, 0.107),
                rot=_WRIST_QUAT_ROS,
                convention="ros",
            ),
        )


##
# VS v4/v5 (no pose_command) evaluation configs — 32D obs space
##

@configclass
class _VSNoCmdPolicyCfg(ObsGroup):
    """32D policy obs without pose_command — matches v4/v5 training checkpoints.

    Layout: joint_pos_rel(9) + joint_vel_rel(9) + image_error(8) + last_action(6) = 32D
    """

    joint_pos = ObsTerm(func=mdp.joint_pos_rel, noise=Unoise(n_min=-0.01, n_max=0.01))
    joint_vel = ObsTerm(func=mdp.joint_vel_rel, noise=Unoise(n_min=-0.01, n_max=0.01))
    image_error = ObsTerm(
        func=mdp.image_error_vs,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=["panda_hand"]),
            "command_name": "ee_pose",
            "feature_half_size": 0.025,
            "hand_eye_offset": (0.0, 0.0, 0.107),
            "fx": 500.0,
            "fy": 500.0,
            "cx": 320.0,
            "cy": 240.0,
            "img_w": 640.0,
            "img_h": 480.0,
        },
    )
    actions = ObsTerm(func=mdp.last_action)

    def __post_init__(self):
        self.enable_corruption = True
        self.concatenate_terms = True


@configclass
class FrankaReachEnvCfg_VS_NoCmd_PLAY(FrankaReachEnvCfg_VS_PLAY):
    """Evaluation config for v4/v5 checkpoints (32D obs, no pose_command).

    Inherits cameras and resampling fix from VS_PLAY; replaces the observation
    group with the no-cmd 32D layout that matches the v4/v5 training configs.
    """

    def __post_init__(self):
        super().__post_init__()
        self.observations.policy = _VSNoCmdPolicyCfg()
        self.observations.policy.enable_corruption = False
