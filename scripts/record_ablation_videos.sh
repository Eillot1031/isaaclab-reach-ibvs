#!/bin/bash
# Record videos and extract screenshots for all 4 ablation variants (50k runs)
set -e

ISAACLAB_DIR="/home/krz/isaaclab_ws/IsaacLab"
SCRIPTS_DIR="/home/krz/isaaclab_ws/scripts"
LOG_BASE="/home/krz/isaaclab_ws/IsaacLab/logs/skrl/reach_franka_sac"
SCREENSHOT_DIR="/home/krz/isaaclab_ws/outputs/screenshots"
OUT_DIR="/home/krz/isaaclab_ws/outputs/logs"

mkdir -p "$SCREENSHOT_DIR"

declare -A RUNS
RUNS["A1"]="2026-05-18_09-48-55_sac_torch"
RUNS["A2"]="2026-05-18_11-25-02_sac_torch"
RUNS["A3"]="2026-05-18_13-02-00_sac_torch"
RUNS["A4"]="2026-05-18_14-39-10_sac_torch"

cd "$ISAACLAB_DIR"

for variant in A1 A2 A3 A4; do
    run_dir="${RUNS[$variant]}"
    ckpt="$LOG_BASE/$run_dir/checkpoints/best_agent.pt"
    log="$OUT_DIR/ablation_${variant}_video.log"

    echo "=========================================="
    echo "  Recording: $variant  ($run_dir)"
    echo "=========================================="

    OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
        "$SCRIPTS_DIR/play_multiview.py" \
        --checkpoint "$ckpt" \
        --num_envs 4 \
        --video_length 360 \
        2>&1 | tee "$log"

    # Extract a frame from the perspective video as screenshot
    VIDEO_DIR="$LOG_BASE/$run_dir/videos/play"
    if [ -f "$VIDEO_DIR/perspective_view.mp4" ]; then
        ffmpeg -y -i "$VIDEO_DIR/perspective_view.mp4" -vframes 1 -ss 00:00:03 \
            "$SCREENSHOT_DIR/ablation_${variant}_perspective_frame.png" 2>/dev/null
        echo "  Screenshot extracted: ablation_${variant}_perspective_frame.png"
    fi
    if [ -f "$VIDEO_DIR/side_view.mp4" ]; then
        ffmpeg -y -i "$VIDEO_DIR/side_view.mp4" -vframes 1 -ss 00:00:03 \
            "$SCREENSHOT_DIR/ablation_${variant}_side_frame.png" 2>/dev/null
        echo "  Screenshot extracted: ablation_${variant}_side_frame.png"
    fi

    echo "  $variant recording complete."
done

echo ""
echo "=========================================="
echo "  All ablation recordings complete!"
echo "=========================================="
