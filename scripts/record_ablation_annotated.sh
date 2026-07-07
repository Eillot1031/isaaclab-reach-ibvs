#!/bin/bash
# Record annotated 10-episode evaluation videos for A0-A4 ablation models.
# Each video shows per-episode return (top-right) and 10-ep mean return (bottom).

ISAACLAB_DIR="/home/krz/isaaclab_ws/IsaacLab"
SCRIPTS_DIR="/home/krz/isaaclab_ws/scripts"
LOG_BASE="/home/krz/isaaclab_ws/IsaacLab/logs/skrl/reach_franka_sac"
OUT_DIR="/home/krz/isaaclab_ws/outputs/videos"
LOG_DIR="/home/krz/isaaclab_ws/outputs/logs"

mkdir -p "$OUT_DIR" "$LOG_DIR"

# A0 = R37 baseline (full model)
declare -A RUNS=(
    ["A0"]="2026-05-13_21-11-26_sac_torch"
    ["A1"]="2026-05-18_09-48-55_sac_torch"
    ["A2"]="2026-05-18_11-25-02_sac_torch"
    ["A3"]="2026-05-18_13-02-00_sac_torch"
    ["A4"]="2026-05-18_14-39-10_sac_torch"
)

declare -A LABELS=(
    ["A0"]="A0: Full Model (Baseline)"
    ["A1"]="A1: No Success Bonus"
    ["A2"]="A2: No Orientation Tracking"
    ["A3"]="A3: No Action Penalties"
    ["A4"]="A4: Position Tracking Only"
)

cd "$ISAACLAB_DIR"

for variant in A0 A1 A2 A3 A4; do
    run_dir="${RUNS[$variant]}"
    label="${LABELS[$variant]}"
    ckpt="$LOG_BASE/$run_dir/checkpoints/best_agent.pt"
    out_video="$OUT_DIR/ablation_${variant}_annotated.mp4"
    log="$LOG_DIR/ablation_${variant}_annotated.log"

    echo "=========================================="
    echo "  Recording annotated: $variant"
    echo "  Label: $label"
    echo "=========================================="

    OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
        "$SCRIPTS_DIR/play_view_annotated.py" \
        --task Isaac-Reach-Franka-IK-Rel-Play-v0 \
        --headless --num_envs 4 --algorithm SAC \
        --num_episodes 10 \
        --view perspective \
        --checkpoint "$ckpt" \
        --label "$label" \
        --out_video "$out_video" \
        2>&1 | tee "$log"

    echo "  $variant done -> $out_video"
done

echo ""
echo "=========================================="
echo "  All annotated recordings complete!"
echo "  Output: $OUT_DIR"
echo "=========================================="
