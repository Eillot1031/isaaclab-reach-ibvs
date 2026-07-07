#!/bin/bash
# VS v2 训练后自动评估 + 录像脚本
# 训练完成后依次执行：
#   1. play_vs.py       — 10 episode 标准评估（含 wrist cam）
#   2. play_tracking_demo.py — 连续跟踪演示（600 步）
#   3. play_singularity_test.py — 180° 奇异点测试（10 episodes）
#
# Usage: bash vs2_post_train.sh [TRAIN_PID]

set -e

TRAIN_PID=${1:-28847}
ISAACLAB=/home/krz/isaaclab_ws/IsaacLab
SCRIPTS=/home/krz/isaaclab_ws/scripts
LOGS=/home/krz/isaaclab_ws/outputs/logs
CKPT_DIR="$ISAACLAB/logs/skrl/reach_franka_sac/2026-06-01_18-08-08_sac_torch/checkpoints"

echo "========================================================"
echo "  VS v2 Post-Train Runner"
echo "  Monitoring PID: $TRAIN_PID"
echo "========================================================"

# ── 等待训练完成 ──────────────────────────────────────────────────────────────
while kill -0 "$TRAIN_PID" 2>/dev/null; do
    STEP=$(ls "$CKPT_DIR"/agent_*.pt 2>/dev/null \
           | grep -oP '(?<=agent_)\d+' | sort -n | tail -1)
    PCT=$(echo "scale=1; ${STEP:-0}*100/400000" | bc 2>/dev/null || echo "?")
    echo "[$(date '+%H:%M:%S')] 训练进行中... step=${STEP:-?}/400000 (${PCT}%)"
    sleep 60
done

echo ""
echo "[$(date '+%H:%M:%S')] ✅ 训练完成！"
echo ""

# ── 确定 best_agent.pt 路径 ───────────────────────────────────────────────────
CKPT=$(find "$CKPT_DIR" -name "best_agent.pt" | head -1)
if [ -z "$CKPT" ]; then
    echo "[ERROR] 找不到 best_agent.pt，退出"
    exit 1
fi
echo "[INFO] 使用检查点: $CKPT"
echo ""

cd "$ISAACLAB"

# ── 1. 标准评估（10 episodes，4 envs，stillness_threshold=0.03）────────────────
echo "========================================================"
echo "  [1/3] 标准评估（play_vs.py）"
echo "========================================================"
OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
    "$SCRIPTS/play_vs.py" \
    --task Isaac-Reach-Franka-VS-Play-v0 \
    --headless --num_envs 4 --algorithm SAC \
    --num_episodes 10 \
    --stillness_threshold 0.03 \
    --checkpoint "$CKPT" \
    2>&1 | tee "$LOGS/eval_vs2_standard.log"

echo ""
echo "[$(date '+%H:%M:%S')] ✅ 标准评估完成"
echo ""

# ── 2. 连续跟踪演示（600 步，1 env）─────────────────────────────────────────
echo "========================================================"
echo "  [2/3] 连续跟踪演示（play_tracking_demo.py）"
echo "========================================================"
OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
    "$SCRIPTS/play_tracking_demo.py" \
    --task Isaac-Reach-Franka-VS-Play-v0 \
    --headless --num_envs 1 --algorithm SAC \
    --total_steps 600 --traj_freq 60 \
    --stillness_threshold 0.03 \
    --checkpoint "$CKPT" \
    2>&1 | tee "$LOGS/eval_vs2_tracking.log"

echo ""
echo "[$(date '+%H:%M:%S')] ✅ 连续跟踪演示完成"
echo ""

# ── 3. 180° 奇异点测试（10 episodes，1 env）──────────────────────────────────
echo "========================================================"
echo "  [3/3] IBVS 180° 奇异点测试（play_singularity_test.py）"
echo "========================================================"
OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
    "$SCRIPTS/play_singularity_test.py" \
    --task Isaac-Reach-Franka-VS-Play-v0 \
    --headless --num_envs 1 --algorithm SAC \
    --num_episodes 10 \
    --stillness_threshold 0.03 \
    --checkpoint "$CKPT" \
    2>&1 | tee "$LOGS/eval_vs2_singularity.log"

echo ""
echo "[$(date '+%H:%M:%S')] ✅ 奇异点测试完成"
echo ""

# ── 汇总 ──────────────────────────────────────────────────────────────────────
echo "========================================================"
echo "  全部完成！输出文件："
echo "  日志: $LOGS/eval_vs2_*.log"
echo "  视频: /home/krz/isaaclab_ws/outputs/videos/"
ls /home/krz/isaaclab_ws/outputs/videos/*.mp4 2>/dev/null | tail -6
echo "========================================================"
