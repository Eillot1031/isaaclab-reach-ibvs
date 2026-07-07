#!/bin/bash
# Auto-eval script for VS v2 model (run after training finishes)
# Usage: bash vs2_eval_after_train.sh <TRAIN_PID>

TRAIN_PID=${1:-28847}
LOG=/home/krz/isaaclab_ws/outputs/logs/train_vs2_50k.log
ISAACLAB=/home/krz/isaaclab_ws/IsaacLab

echo "[INFO] Waiting for training PID $TRAIN_PID to finish..."
while kill -0 "$TRAIN_PID" 2>/dev/null; do
    sleep 30
    LATEST=$(grep "Best agent" "$LOG" 2>/dev/null | tail -1 || echo "N/A")
    echo "[MONITOR] $(date '+%H:%M:%S') | $LATEST"
done

echo "[INFO] Training done! Finding best checkpoint..."
CKPT=$(find "$ISAACLAB/logs/skrl" -name "best_agent.pt" -newer "$LOG" 2>/dev/null \
       | sort -t '/' -k8 | tail -1)

if [ -z "$CKPT" ]; then
    CKPT=$(find "$ISAACLAB/logs/skrl" -path "*/Isaac-Reach-Franka-VS*" -name "best_agent.pt" \
           | sort | tail -1)
fi

echo "[INFO] Checkpoint: $CKPT"

cd "$ISAACLAB"
OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
    ../scripts/play_vs.py \
    --task Isaac-Reach-Franka-VS-Play-v0 \
    --headless --num_envs 4 --algorithm SAC \
    --num_episodes 10 \
    --stillness_threshold 0.03 \
    --checkpoint "$CKPT" \
    2>&1 | tee /home/krz/isaaclab_ws/outputs/logs/eval_vs2.log

echo "[INFO] Evaluation done. See outputs/logs/eval_vs2.log"
echo "[INFO] Next: run tracking demo and singularity test with the new checkpoint."
echo "  Checkpoint: $CKPT"
