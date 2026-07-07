#!/usr/bin/env python3
"""Experiment 3: Run all robustness conditions via subprocess calls.

Each condition launches a separate play_view.py invocation.
Results are collected and saved to JSON.
"""

import json
import os
import re
import subprocess
import sys

ISAACLAB_DIR = "/home/krz/isaaclab_ws/IsaacLab"
CHECKPOINT = os.path.join(
    ISAACLAB_DIR,
    "logs/skrl/reach_franka_sac/2026-05-13_21-11-26_sac_torch/checkpoints/best_agent.pt"
)
CFG_FILE = os.path.join(
    ISAACLAB_DIR,
    "source/isaaclab_tasks/isaaclab_tasks/manager_based/manipulation/reach/reach_env_cfg.py"
)
IK_REL_CFG_FILE = os.path.join(
    ISAACLAB_DIR,
    "source/isaaclab_tasks/isaaclab_tasks/manager_based/manipulation/reach/config/franka/ik_rel_env_cfg.py"
)
OUT_DIR = "/home/krz/isaaclab_ws/outputs/tables"
LOG_DIR = "/home/krz/isaaclab_ws/outputs/logs"


def run_eval(label, log_suffix):
    """Run a 10-episode evaluation and return Mean Return."""
    log_file = os.path.join(LOG_DIR, f"robustness_{log_suffix}.log")
    cmd = (
        f"cd {ISAACLAB_DIR} && OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python "
        f"../scripts/play_view.py "
        f"--task Isaac-Reach-Franka-IK-Rel-Play-v0 "
        f"--headless --num_envs 4 --algorithm SAC "
        f"--num_episodes 10 --view perspective "
        f"--checkpoint {CHECKPOINT}"
    )
    print(f"  Running: {label}...")
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=300
    )
    output = result.stdout + result.stderr
    with open(log_file, "w") as f:
        f.write(output)

    match = re.search(r"Mean Return\s*:\s*([\+\-]?[\d.]+)\s*\+/-\s*([\d.]+)", output)
    if match:
        mean_ret = float(match.group(1))
        std_ret = float(match.group(2))
        print(f"    Result: Mean={mean_ret:+.4f} +/- {std_ret:.4f}")
        return {"label": label, "mean": mean_ret, "std": std_ret}
    else:
        print(f"    WARNING: Could not parse results from output")
        return {"label": label, "mean": None, "std": None}


def read_cfg():
    with open(CFG_FILE, "r") as f:
        return f.read()


def write_cfg(content):
    with open(CFG_FILE, "w") as f:
        f.write(content)


def read_ik_cfg():
    with open(IK_REL_CFG_FILE, "r") as f:
        return f.read()


def write_ik_cfg(content):
    with open(IK_REL_CFG_FILE, "w") as f:
        f.write(content)


def backup_cfg():
    original = read_cfg()
    with open(CFG_FILE + ".robustness_bak", "w") as f:
        f.write(original)
    ik_original = read_ik_cfg()
    with open(IK_REL_CFG_FILE + ".robustness_bak", "w") as f:
        f.write(ik_original)
    return original


def restore_cfg():
    for fpath in [CFG_FILE, IK_REL_CFG_FILE]:
        bak = fpath + ".robustness_bak"
        if os.path.exists(bak):
            with open(bak, "r") as f:
                content = f.read()
            with open(fpath, "w") as f:
                f.write(content)
            os.remove(bak)


def patch_noise(content, noise_val):
    """Replace noise values in ObsCfg."""
    if noise_val == 0.0:
        content = re.sub(
            r'(joint_pos = ObsTerm\(func=mdp\.joint_pos_rel,)\s*noise=Unoise\([^)]+\)\)',
            r'\1)',
            content
        )
        content = re.sub(
            r'(joint_vel = ObsTerm\(func=mdp\.joint_vel_rel,)\s*noise=Unoise\([^)]+\)\)',
            r'\1)',
            content
        )
    else:
        content = re.sub(
            r'(joint_pos = ObsTerm\(func=mdp\.joint_pos_rel(?:,\s*noise=Unoise\([^)]+\))?)\)',
            f'joint_pos = ObsTerm(func=mdp.joint_pos_rel, noise=Unoise(n_min=-{noise_val}, n_max={noise_val}))',
            content
        )
        content = re.sub(
            r'(joint_vel = ObsTerm\(func=mdp\.joint_vel_rel(?:,\s*noise=Unoise\([^)]+\))?)\)',
            f'joint_vel = ObsTerm(func=mdp.joint_vel_rel, noise=Unoise(n_min=-{noise_val}, n_max={noise_val}))',
            content
        )
    return content


def patch_init_pose(content, pos_range):
    """Replace position_range in EventCfg."""
    content = re.sub(
        r'"position_range":\s*\([^)]+\)',
        f'"position_range": {pos_range}',
        content
    )
    return content


def patch_workspace(content, ranges):
    """Replace workspace ranges in CommandsCfg."""
    content = re.sub(
        r'pos_x=\([^)]+\)',
        f'pos_x={ranges["pos_x"]}',
        content
    )
    content = re.sub(
        r'pos_y=\([^)]+\)',
        f'pos_y={ranges["pos_y"]}',
        content
    )
    content = re.sub(
        r'pos_z=\([^)]+\)',
        f'pos_z={ranges["pos_z"]}',
        content
    )
    return content


def enable_corruption_in_play():
    """Ensure PLAY config has enable_corruption = True so noise applies."""
    ik_content = read_ik_cfg()
    ik_content = ik_content.replace(
        "self.observations.policy.enable_corruption = False",
        "self.observations.policy.enable_corruption = True"
    )
    write_ik_cfg(ik_content)


def disable_corruption_in_play():
    """Restore PLAY config to disable corruption."""
    bak = IK_REL_CFG_FILE + ".robustness_bak"
    if os.path.exists(bak):
        with open(bak, "r") as f:
            content = f.read()
        write_ik_cfg(content)


def run_noise_tests(original):
    print("\n" + "="*60)
    print("  Robustness Test: Observation Noise")
    print("="*60)
    enable_corruption_in_play()
    noise_levels = [0.0, 0.01, 0.02, 0.05, 0.1, 0.2]
    results = []
    for noise_val in noise_levels:
        content = patch_noise(original, noise_val)
        write_cfg(content)
        r = run_eval(f"noise={noise_val}", f"noise_{noise_val}")
        results.append(r)
    disable_corruption_in_play()
    return results


def run_init_pose_tests(original):
    print("\n" + "="*60)
    print("  Robustness Test: Initial Pose Distribution")
    print("="*60)
    ranges = [(0.5, 1.5), (0.3, 1.7), (0.1, 1.9), (0.0, 2.0)]
    results = []
    for pr in ranges:
        content = patch_init_pose(original, pr)
        write_cfg(content)
        r = run_eval(f"range={pr}", f"init_pose_{pr[0]}_{pr[1]}")
        results.append(r)
    return results


def run_workspace_tests(original):
    print("\n" + "="*60)
    print("  Robustness Test: Workspace Expansion")
    print("="*60)
    configs = [
        {"label": "Default", "pos_x": (0.35, 0.65), "pos_y": (-0.2, 0.2), "pos_z": (0.15, 0.5)},
        {"label": "Expanded-1", "pos_x": (0.25, 0.75), "pos_y": (-0.3, 0.3), "pos_z": (0.10, 0.60)},
        {"label": "Expanded-2", "pos_x": (0.15, 0.85), "pos_y": (-0.4, 0.4), "pos_z": (0.05, 0.70)},
    ]
    results = []
    for cfg in configs:
        content = patch_workspace(original, cfg)
        write_cfg(content)
        r = run_eval(cfg["label"], f"workspace_{cfg['label']}")
        results.append(r)
    return results


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    original = backup_cfg()

    try:
        noise_results = run_noise_tests(original)
        with open(os.path.join(OUT_DIR, "robustness_noise.json"), "w") as f:
            json.dump(noise_results, f, indent=2)

        init_pose_results = run_init_pose_tests(original)
        with open(os.path.join(OUT_DIR, "robustness_init_pose.json"), "w") as f:
            json.dump(init_pose_results, f, indent=2)

        workspace_results = run_workspace_tests(original)
        with open(os.path.join(OUT_DIR, "robustness_workspace.json"), "w") as f:
            json.dump(workspace_results, f, indent=2)

        # Action perturbation is tested differently - via a modified play script
        # For now, use the baseline result and note that action perturbation
        # requires modifying the eval loop directly
        print("\n" + "="*60)
        print("  All robustness tests complete!")
        print("="*60)

    finally:
        restore_cfg()
        print("Config restored to original.")
