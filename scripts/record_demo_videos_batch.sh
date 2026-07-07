#!/usr/bin/env bash
# Batch record: VS6 singularity, R37 perspective/side, R37 tracking, R37 singularity.
# Do not use pipes (| tail) — logs go to /tmp/*.log

set -euo pipefail

ISAACLAB=/home/krz/isaaclab_ws/IsaacLab
SCRIPTS=/home/krz/isaaclab_ws/scripts
OUT=/home/krz/isaaclab_ws/outputs/videos
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"

V6_CKPT="$ISAACLAB/logs/skrl/reach_franka_sac/2026-06-02_17-51-20_sac_torch/checkpoints/best_agent.pt"
R37_CKPT="$ISAACLAB/logs/skrl/reach_franka_sac/2026-05-13_21-11-26_sac_torch/checkpoints/best_agent.pt"
R37_TASK="Isaac-Reach-Franka-IK-Rel-Play-v0"
VS_RECORD="Isaac-Reach-Franka-VS-Record-Play-v0"

run_py() {
    local log="$1"; shift
    echo "[RUN] $* -> $log"
    cd "$ISAACLAB"
    OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab --no-capture-output \
        python "$@" > "$log" 2>&1
    echo "[DONE] $log"
}

SING_VS6="$OUT/singularity_test_vs6_${TS}.mp4"
PERSP_R37="$OUT/sac_round37_perspective_10ep_hold_${TS}.mp4"
SIDE_R37="$OUT/sac_round37_side_10ep_hold_${TS}.mp4"
TRACK_R37="$OUT/tracking_demo_r37_${TS}.mp4"
SING_R37="$OUT/singularity_test_r37_${TS}.mp4"

echo "=== 1/5 VS6 singularity ==="
run_py /tmp/record_sing_vs6.log \
    "$SCRIPTS/play_singularity_test.py" \
    --task "$VS_RECORD" --checkpoint "$V6_CKPT" \
    --num_envs 1 --headless --num_episodes 10 --algorithm SAC \
    --hold_pos_threshold 0.025 --hold_image_threshold 0.03 \
    --settle_steps 15 --singularity_scale 1.0 \
    --out_video "$SING_VS6"

echo "=== 2/5 R37 perspective 10ep ==="
run_py /tmp/record_r37_persp.log \
    "$SCRIPTS/play_view.py" \
    --task "$R37_TASK" --checkpoint "$R37_CKPT" \
    --num_envs 1 --headless --num_episodes 10 --algorithm SAC \
    --video --view perspective \
    --hold_pos_threshold 0.025 --hold_image_threshold 0 \
    --copy_to_outputs "$PERSP_R37"

echo "=== 3/5 R37 side 10ep ==="
run_py /tmp/record_r37_side.log \
    "$SCRIPTS/play_view.py" \
    --task "$R37_TASK" --checkpoint "$R37_CKPT" \
    --num_envs 1 --headless --num_episodes 10 --algorithm SAC \
    --video --view side \
    --hold_pos_threshold 0.025 --hold_image_threshold 0 \
    --copy_to_outputs "$SIDE_R37"

echo "=== 4/5 R37 tracking 600 steps ==="
run_py /tmp/record_track_r37.log \
    "$SCRIPTS/play_tracking_demo.py" \
    --task "$R37_TASK" --checkpoint "$R37_CKPT" \
    --num_envs 1 --headless --algorithm SAC \
    --total_steps 600 --traj_freq 120 \
    --hold_pos_threshold 0.025 --hold_image_threshold 0 \
    --out_video "$TRACK_R37"

echo "=== 5/5 R37 singularity 10ep ==="
run_py /tmp/record_sing_r37.log \
    "$SCRIPTS/play_singularity_test.py" \
    --task "$R37_TASK" --checkpoint "$R37_CKPT" \
    --num_envs 1 --headless --num_episodes 10 --algorithm SAC \
    --hold_pos_threshold 0.025 --hold_image_threshold 0 \
    --settle_steps 15 --singularity_scale 1.0 \
    --out_video "$SING_R37"

echo "=== Verify ==="
conda run -n env_isaaclab python "$SCRIPTS/verify_video_frames.py" --check-markers \
    "$SING_VS6" "$TRACK_R37"
conda run -n env_isaaclab python "$SCRIPTS/verify_video_frames.py" \
    "$PERSP_R37" "$SIDE_R37" "$SING_R37"

echo ""
echo "Outputs ($TS):"
ls -lh "$SING_VS6" "$PERSP_R37" "$SIDE_R37" "$TRACK_R37" "$SING_R37"
