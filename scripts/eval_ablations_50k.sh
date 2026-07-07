#!/bin/bash
# Evaluate all 4 ablation variants (50k runs)
set -e

ISAACLAB_DIR="/home/krz/isaaclab_ws/IsaacLab"
SCRIPTS_DIR="/home/krz/isaaclab_ws/scripts"
LOG_BASE="/home/krz/isaaclab_ws/IsaacLab/logs/skrl/reach_franka_sac"
OUT_DIR="/home/krz/isaaclab_ws/outputs/logs"

declare -A RUNS
RUNS["A1"]="2026-05-18_09-48-55_sac_torch"
RUNS["A2"]="2026-05-18_11-25-02_sac_torch"
RUNS["A3"]="2026-05-18_13-02-00_sac_torch"
RUNS["A4"]="2026-05-18_14-39-10_sac_torch"

cd "$ISAACLAB_DIR"

for variant in A1 A2 A3 A4; do
    run_dir="${RUNS[$variant]}"
    ckpt="$LOG_BASE/$run_dir/checkpoints/best_agent.pt"
    log="$OUT_DIR/ablation_${variant}_50k_eval.log"

    echo "=========================================="
    echo "  Evaluating: $variant  ($run_dir)"
    echo "=========================================="

    OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
        "$SCRIPTS_DIR/play_view.py" \
        --task Isaac-Reach-Franka-IK-Rel-Play-v0 \
        --headless --num_envs 4 --algorithm SAC \
        --num_episodes 10 \
        --checkpoint "$ckpt" \
        2>&1 | tee "$log"

    echo "  $variant evaluation complete."
done

echo ""
echo "=========================================="
echo "  All ablation evaluations complete!"
echo "=========================================="
