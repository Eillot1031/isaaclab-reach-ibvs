#!/bin/bash
# Wait for VS training (PID 18013) to finish, then auto-evaluate.
set -e

TRAIN_PID=18013
VS_RUN="2026-06-01_15-30-17_sac_torch"
ISAACLAB_DIR="/home/krz/isaaclab_ws/IsaacLab"
SCRIPTS_DIR="/home/krz/isaaclab_ws/scripts"
CKPT="$ISAACLAB_DIR/logs/skrl/reach_franka_sac/$VS_RUN/checkpoints/best_agent.pt"
LOG="$ISAACLAB_DIR/logs/skrl/reach_franka_sac/$VS_RUN/eval_vs.log"

echo "[MONITOR] Waiting for training PID $TRAIN_PID to finish..."
while kill -0 "$TRAIN_PID" 2>/dev/null; do
    sleep 30
    LATEST=$(ls -t "$ISAACLAB_DIR/logs/skrl/reach_franka_sac/$VS_RUN/checkpoints/"agent_*.pt 2>/dev/null | head -1)
    echo "[MONITOR $(date '+%H:%M:%S')] Latest checkpoint: $(basename $LATEST)"
done

echo "[MONITOR] Training finished at $(date). Starting evaluation..."

# Remove leftover lock files if any
rm -rf /home/krz/miniconda3/envs/env_isaaclab/lib/python3.11/site-packages/isaacsim/kit/cache/DerivedDataCache/app_instance_lock* 2>/dev/null || true

cd "$ISAACLAB_DIR"
OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
    "$SCRIPTS_DIR/play_vs.py" \
    --task Isaac-Reach-Franka-VS-Play-v0 \
    --headless --num_envs 4 --algorithm SAC \
    --num_episodes 10 \
    --checkpoint "$CKPT" \
    2>&1 | tee "$LOG"

echo "[EVAL DONE] Log: $LOG"
