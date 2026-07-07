#!/bin/bash
# Multi-angle video recording using the official SKRL play.py.
# Runs the play script twice (two Isaac Sim sessions) with different camera angles.
#
# Usage:
#   bash scripts/run_multiview_play.sh <checkpoint_path>
#
# Example:
#   cd /home/krz/isaaclab_ws
#   bash scripts/run_multiview_play.sh \
#     IsaacLab/logs/skrl/reach_franka_sac/2026-05-11_13-42-34_sac_torch/checkpoints/best_agent.pt

set -e

CHECKPOINT="${1:?Usage: $0 <checkpoint_path>}"
CHECKPOINT="$(realpath "$CHECKPOINT")"

if [[ ! -f "$CHECKPOINT" ]]; then
    echo "[ERROR] Checkpoint not found: $CHECKPOINT"
    exit 1
fi

RUN_DIR="$(dirname "$(dirname "$CHECKPOINT")")"   # …/checkpoints/../../ = run dir
VIDEO_DIR="$RUN_DIR/videos/play_multiview"
mkdir -p "$VIDEO_DIR"

PLAY_SCRIPT="$(dirname "$(realpath "$0")")/../IsaacLab/scripts/reinforcement_learning/skrl/play.py"
cd "$(dirname "$PLAY_SCRIPT")/../.."   # cd to IsaacLab root

echo "============================================================"
echo "  Multi-view recording"
echo "  Checkpoint : $CHECKPOINT"
echo "  Output dir : $VIDEO_DIR"
echo "============================================================"

# ── View 1: Top-down ──────────────────────────────────────────────────────
echo ""
echo "[1/2] Top-down view (bird's-eye, directly above workspace)..."
OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
    scripts/reinforcement_learning/skrl/play.py \
    --task Isaac-Reach-Franka-Play-v0 \
    --headless \
    --num_envs 4 \
    --algorithm SAC \
    --video \
    --video_length 300 \
    --checkpoint "$CHECKPOINT" \
    "viewer.eye=[0.5,0.0,4.0]" "viewer.lookat=[0.5,0.0,0.0]" \
    2>&1 | tee "$VIDEO_DIR/play_top_view.log"

# Find and rename the generated video
LATEST_VIDEO=$(find "$RUN_DIR/videos" -name "*.mp4" -newer "$RUN_DIR/videos/play_multiview" 2>/dev/null | head -1)
if [[ -n "$LATEST_VIDEO" && "$LATEST_VIDEO" != "$VIDEO_DIR/"* ]]; then
    cp "$LATEST_VIDEO" "$VIDEO_DIR/top_view.mp4"
    echo "[INFO] Top-down video: $VIDEO_DIR/top_view.mp4"
else
    # Try the default play directory
    PLAY_VIDEO=$(find "$RUN_DIR/videos/play" -name "*.mp4" 2>/dev/null | sort -t- -k1 | tail -1)
    if [[ -n "$PLAY_VIDEO" ]]; then
        cp "$PLAY_VIDEO" "$VIDEO_DIR/top_view.mp4"
        echo "[INFO] Top-down video: $VIDEO_DIR/top_view.mp4"
    fi
fi

# ── View 2: Side view ─────────────────────────────────────────────────────
echo ""
echo "[2/2] Side view (from the right, showing robot arm profile)..."
OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
    scripts/reinforcement_learning/skrl/play.py \
    --task Isaac-Reach-Franka-Play-v0 \
    --headless \
    --num_envs 4 \
    --algorithm SAC \
    --video \
    --video_length 300 \
    --checkpoint "$CHECKPOINT" \
    "viewer.eye=[3.5,0.0,1.5]" "viewer.lookat=[0.5,0.0,0.5]" \
    2>&1 | tee "$VIDEO_DIR/play_side_view.log"

# Find and rename the generated video
SIDE_VIDEO=$(find "$RUN_DIR/videos/play" -name "*.mp4" 2>/dev/null | sort -t- -k1 | tail -1)
if [[ -n "$SIDE_VIDEO" ]]; then
    cp "$SIDE_VIDEO" "$VIDEO_DIR/side_view.mp4"
    echo "[INFO] Side view video: $VIDEO_DIR/side_view.mp4"
fi

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Recording complete!"
ls -lh "$VIDEO_DIR/"*.mp4 2>/dev/null || echo "  (no .mp4 files found in $VIDEO_DIR)"
echo "============================================================"
