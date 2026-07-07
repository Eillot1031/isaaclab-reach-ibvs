#!/bin/bash
# Record single-view videos for A1-A4 ablation variants using play_view.py
# Uses perspective view for each

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
    echo "  Recording: $variant"
    echo "=========================================="

    OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
        "$SCRIPTS_DIR/play_view.py" \
        --task Isaac-Reach-Franka-IK-Rel-Play-v0 \
        --headless --num_envs 4 --algorithm SAC \
        --video --num_episodes 3 \
        --view perspective \
        --checkpoint "$ckpt" \
        2>&1 | tee "$log"

    # Extract screenshot from the generated video
    VIDEO_GLOB="$LOG_BASE/$run_dir/videos/play/*.mp4"
    LATEST_VIDEO=$(ls -t $VIDEO_GLOB 2>/dev/null | head -1)
    if [ -n "$LATEST_VIDEO" ]; then
        ffmpeg -y -i "$LATEST_VIDEO" -vf "select=eq(n\,90)" -vsync vfr \
            "$SCREENSHOT_DIR/ablation_${variant}_frame.png" 2>/dev/null && \
            echo "  Screenshot: ablation_${variant}_frame.png"
    fi

    echo "  $variant complete."
done

echo ""
echo "All ablation recordings complete!"
