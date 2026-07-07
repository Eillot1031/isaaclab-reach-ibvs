#!/usr/bin/env bash
# Post-training pipeline for VS v4
# Usage: bash vs4_post_train.sh <training_pid> <log_dir>
set -euo pipefail

TRAIN_PID=${1:-78997}
LOG_DIR=${2:-"/home/krz/isaaclab_ws/IsaacLab/logs/skrl/reach_franka_sac/2026-06-02_10-41-01_sac_torch"}
ISAACLAB_DIR="/home/krz/isaaclab_ws/IsaacLab"
SCRIPTS_DIR="/home/krz/isaaclab_ws/scripts"
VIDEO_DIR="/home/krz/isaaclab_ws/outputs/videos"
TS=$(date +%Y%m%d_%H%M%S)

echo "[$(date)] Waiting for training PID $TRAIN_PID to finish..."
while kill -0 "$TRAIN_PID" 2>/dev/null; do
    sleep 60
    CKPTS=$(ls "$LOG_DIR/checkpoints/"*.pt 2>/dev/null | wc -l)
    LATEST=$(ls -t "$LOG_DIR/checkpoints/"*.pt 2>/dev/null | head -1 | xargs basename 2>/dev/null || echo "none")
    echo "[$(date)] Training running... checkpoints=$CKPTS, latest=$LATEST"
done
echo "[$(date)] Training finished."

# Step 1: Evaluate best checkpoint
BEST_CKPT="$LOG_DIR/checkpoints/best_agent.pt"
if [ ! -f "$BEST_CKPT" ]; then
    echo "ERROR: No best_agent.pt found in $LOG_DIR/checkpoints/"
    exit 1
fi

echo "[$(date)] Evaluating best checkpoint: $BEST_CKPT"
EVAL_OUT=$(conda run -n env_isaaclab python "$SCRIPTS_DIR/play_vs.py" \
    --task Isaac-Reach-Franka-VS-v0 \
    --num_envs 8 \
    --headless \
    --checkpoint "$BEST_CKPT" \
    --num_episodes 20 \
    --stillness_threshold 0.03 \
    2>&1)
echo "$EVAL_OUT"

MEAN_POS=$(echo "$EVAL_OUT" | grep -oP 'Mean Final Pos Error: \K[0-9.]+' | head -1)
if [ -z "$MEAN_POS" ]; then
    echo "ERROR: Could not parse Mean Final Pos Error from evaluation output."
    exit 1
fi

echo "[$(date)] Mean Final Pos Error: ${MEAN_POS} cm"

# Check qualification threshold
THRESHOLD=3.5
QUALIFIED=$(python3 -c "print('yes' if float('${MEAN_POS}') < ${THRESHOLD} else 'no')")

if [ "$QUALIFIED" != "yes" ]; then
    echo "[$(date)] ❌ NOT QUALIFIED: ${MEAN_POS} cm >= ${THRESHOLD} cm. Need further optimization."
    exit 1
fi

echo "[$(date)] ✅ QUALIFIED: ${MEAN_POS} cm < ${THRESHOLD} cm. Recording videos..."
mkdir -p "$VIDEO_DIR"

# Step 2: Standard videos (perspective + wrist cam + composite)
echo "[$(date)] Recording standard 10-episode videos..."
conda run -n env_isaaclab python "$SCRIPTS_DIR/play_vs.py" \
    --task Isaac-Reach-Franka-VS-v0 \
    --num_envs 1 \
    --checkpoint "$BEST_CKPT" \
    --num_episodes 10 \
    --stillness_threshold 0.03 \
    --video \
    2>&1 | tee /tmp/play_vs_video.log

# Copy videos
for f in outputs/vs_eval_perspective.mp4 outputs/vs_eval_wristcam.mp4 outputs/vs_eval_composite.mp4; do
    [ -f "$ISAACLAB_DIR/$f" ] && cp "$ISAACLAB_DIR/$f" "$VIDEO_DIR/vs4_${TS}_$(basename $f)"
done

# Step 3: Tracking demo
echo "[$(date)] Recording tracking demo..."
conda run -n env_isaaclab python "$SCRIPTS_DIR/play_tracking_demo.py" \
    --task Isaac-Reach-Franka-VS-v0 \
    --num_envs 1 \
    --checkpoint "$BEST_CKPT" \
    --stillness_threshold 0.03 \
    2>&1 | tee /tmp/play_tracking.log

[ -f "$SCRIPTS_DIR/outputs/tracking_demo.mp4" ] && \
    cp "$SCRIPTS_DIR/outputs/tracking_demo.mp4" "$VIDEO_DIR/vs4_${TS}_tracking_demo.mp4"

# Step 4: Singularity test
echo "[$(date)] Running IBVS 180° singularity test..."
SING_OUT=$(conda run -n env_isaaclab python "$SCRIPTS_DIR/play_singularity_test.py" \
    --task Isaac-Reach-Franka-VS-v0 \
    --num_envs 1 \
    --checkpoint "$BEST_CKPT" \
    --num_episodes 20 \
    --stillness_threshold 0.03 \
    2>&1 | tee /tmp/play_singularity.log)
echo "$SING_OUT"

RETREAT_PCT=$(echo "$SING_OUT" | grep -oP 'Back-Retreat: \K[0-9.]+' | head -1)
[ -f "$SCRIPTS_DIR/outputs/singularity_test.mp4" ] && \
    cp "$SCRIPTS_DIR/outputs/singularity_test.mp4" "$VIDEO_DIR/vs4_${TS}_singularity_test.mp4"

echo ""
echo "========================================"
echo "VS v4 Post-Train Pipeline Summary"
echo "========================================"
echo "Mean Final Pos Error: ${MEAN_POS} cm (threshold: ${THRESHOLD} cm)"
echo "Back-Retreat Rate: ${RETREAT_PCT:-N/A}%"
echo "Videos saved to: $VIDEO_DIR"
echo "========================================"

if [ -n "$RETREAT_PCT" ] && python3 -c "exit(0 if float('${RETREAT_PCT}') > 50 else 1)"; then
    echo "⚠️  WARNING: Back-Retreat rate ${RETREAT_PCT}% > 50%. Consider anti_retreat optimization."
fi
