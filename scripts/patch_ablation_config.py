#!/usr/bin/env python3
"""Patch reach_env_cfg.py for ablation experiments.

Usage: python patch_ablation_config.py <A1|A2|A3|A4|RESTORE>
"""
import sys
import re

CFG = "/home/krz/isaaclab_ws/IsaacLab/source/isaaclab_tasks/isaaclab_tasks/manager_based/manipulation/reach/reach_env_cfg.py"

# Original values (Round 37 baseline)
ORIG = {
    "position_tracking_weight": -0.2,
    "fine_grained_weight": 0.5,
    "orientation_weight": -0.3,
    "reach_success_weight": 1.0,
    "action_rate_weight": -0.0001,
    "joint_vel_weight": -0.0001,
    "curriculum_action_rate_weight": -0.001,
    "curriculum_joint_vel_weight": -0.0005,
}

def read_cfg():
    with open(CFG, "r") as f:
        return f.read()

def write_cfg(content):
    with open(CFG, "w") as f:
        f.write(content)

def restore_baseline():
    """Restore all weights to Round 37 baseline values."""
    content = read_cfg()
    # Restore from backup if exists
    import os
    bak = CFG + ".bak"
    if os.path.exists(bak):
        with open(bak, "r") as f:
            content = f.read()
        write_cfg(content)
        print("Restored from backup.")
    else:
        print("No backup found.")

def patch_a1():
    """A1: No reach_success bonus -- set reach_success weight to 0."""
    restore_from_bak()
    content = read_cfg()
    content = re.sub(
        r'(reach_success = RewTerm\(\s*func=mdp\.reach_success_bonus,\s*weight=)[\d.]+',
        r'\g<1>0.0',
        content
    )
    write_cfg(content)
    print("A1 patched: reach_success.weight = 0.0")

def patch_a2():
    """A2: No orientation tracking -- set orientation weight to 0."""
    restore_from_bak()
    content = read_cfg()
    content = re.sub(
        r'(end_effector_orientation_tracking = RewTerm\(\s*func=mdp\.orientation_command_error,\s*weight=)[-\d.]+',
        r'\g<1>0.0',
        content
    )
    write_cfg(content)
    print("A2 patched: orientation_tracking.weight = 0.0")

def patch_a3():
    """A3: No action penalties -- action_rate=0, joint_vel=0, disable curriculum."""
    restore_from_bak()
    content = read_cfg()
    # Zero out action_rate weight
    content = re.sub(
        r'(action_rate = RewTerm\(func=mdp\.action_rate_l2, weight=)[-\d.]+',
        r'\g<1>0.0',
        content
    )
    # Zero out joint_vel weight
    content = re.sub(
        r'(joint_vel = RewTerm\(\s*func=mdp\.joint_vel_l2,\s*weight=)[-\d.]+',
        r'\g<1>0.0',
        content
    )
    # Disable curriculum by setting target weights to 0
    content = re.sub(
        r'(action_rate = CurrTerm\(\s*func=mdp\.modify_reward_weight, params=\{"term_name": "action_rate", "weight": )[-\d.]+',
        r'\g<1>0.0',
        content
    )
    content = re.sub(
        r'(joint_vel = CurrTerm\(\s*func=mdp\.modify_reward_weight, params=\{"term_name": "joint_vel", "weight": )[-\d.]+',
        r'\g<1>0.0',
        content
    )
    write_cfg(content)
    print("A3 patched: action_rate=0, joint_vel=0, curriculum disabled")

def patch_a4():
    """A4: Only position tracking -- keep position L2 + fine_grained, zero everything else."""
    restore_from_bak()
    content = read_cfg()
    # Zero orientation
    content = re.sub(
        r'(end_effector_orientation_tracking = RewTerm\(\s*func=mdp\.orientation_command_error,\s*weight=)[-\d.]+',
        r'\g<1>0.0',
        content
    )
    # Zero reach_success
    content = re.sub(
        r'(reach_success = RewTerm\(\s*func=mdp\.reach_success_bonus,\s*weight=)[\d.]+',
        r'\g<1>0.0',
        content
    )
    # Zero action_rate
    content = re.sub(
        r'(action_rate = RewTerm\(func=mdp\.action_rate_l2, weight=)[-\d.]+',
        r'\g<1>0.0',
        content
    )
    # Zero joint_vel
    content = re.sub(
        r'(joint_vel = RewTerm\(\s*func=mdp\.joint_vel_l2,\s*weight=)[-\d.]+',
        r'\g<1>0.0',
        content
    )
    # Disable curriculum
    content = re.sub(
        r'(action_rate = CurrTerm\(\s*func=mdp\.modify_reward_weight, params=\{"term_name": "action_rate", "weight": )[-\d.]+',
        r'\g<1>0.0',
        content
    )
    content = re.sub(
        r'(joint_vel = CurrTerm\(\s*func=mdp\.modify_reward_weight, params=\{"term_name": "joint_vel", "weight": )[-\d.]+',
        r'\g<1>0.0',
        content
    )
    write_cfg(content)
    print("A4 patched: only position tracking (L2 + fine_grained), all else zeroed")

def restore_from_bak():
    import os
    bak = CFG + ".bak"
    if os.path.exists(bak):
        with open(bak, "r") as f:
            content = f.read()
        write_cfg(content)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python patch_ablation_config.py <A1|A2|A3|A4|RESTORE>")
        sys.exit(1)
    
    variant = sys.argv[1].upper()
    if variant == "A1":
        patch_a1()
    elif variant == "A2":
        patch_a2()
    elif variant == "A3":
        patch_a3()
    elif variant == "A4":
        patch_a4()
    elif variant == "RESTORE":
        restore_baseline()
    else:
        print(f"Unknown variant: {variant}")
        sys.exit(1)
