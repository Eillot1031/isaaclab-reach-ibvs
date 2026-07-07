#!/bin/bash
# Ablation experiment runner
# Runs 4 ablation variants sequentially, each with 10k iterations
# Uses a Python helper to patch reward weights before each run

set -e

ISAACLAB_DIR="/home/krz/isaaclab_ws/IsaacLab"
SCRIPTS_DIR="/home/krz/isaaclab_ws/scripts"
CFG_FILE="$ISAACLAB_DIR/source/isaaclab_tasks/isaaclab_tasks/manager_based/manipulation/reach/reach_env_cfg.py"
CURRICULUM_BACKUP=""

cd "$ISAACLAB_DIR"

# Save original config
cp "$CFG_FILE" "${CFG_FILE}.bak"

echo "=========================================="
echo "  Ablation Experiment Runner"
echo "=========================================="

run_ablation() {
    local variant_name="$1"
    local desc="$2"
    
    echo ""
    echo "=========================================="
    echo "  Running: $variant_name - $desc"
    echo "=========================================="
    
    OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
        scripts/reinforcement_learning/skrl/train.py \
        --task Isaac-Reach-Franka-IK-Rel-v0 \
        --headless --num_envs 512 --algorithm SAC \
        --max_iterations 50000 \
        2>&1 | tee "/home/krz/isaaclab_ws/outputs/logs/ablation_${variant_name}.log"
    
    echo "  $variant_name training complete."
}

# A1: No reach_success bonus (weight=0)
echo "Patching config for A1: reach_success.weight = 0"
conda run -n env_isaaclab python "$SCRIPTS_DIR/patch_ablation_config.py" A1
run_ablation "A1_no_success" "No reach_success bonus"

# A2: No orientation tracking (weight=0) 
echo "Patching config for A2: orientation_tracking.weight = 0"
conda run -n env_isaaclab python "$SCRIPTS_DIR/patch_ablation_config.py" A2
run_ablation "A2_no_orientation" "No orientation tracking"

# A3: No action penalties (action_rate=0, joint_vel=0, no curriculum)
echo "Patching config for A3: action_rate=0, joint_vel=0, no curriculum"
conda run -n env_isaaclab python "$SCRIPTS_DIR/patch_ablation_config.py" A3
run_ablation "A3_no_action_penalty" "No action penalties"

# A4: Only position tracking (dense only)
echo "Patching config for A4: only position tracking"
conda run -n env_isaaclab python "$SCRIPTS_DIR/patch_ablation_config.py" A4
run_ablation "A4_position_only" "Only position tracking (dense)"

# Restore original config
echo ""
echo "Restoring original config..."
cp "${CFG_FILE}.bak" "$CFG_FILE"
rm "${CFG_FILE}.bak"

echo ""
echo "=========================================="
echo "  All ablation training complete!"
echo "=========================================="
