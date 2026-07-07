#!/usr/bin/env bash
# Sequential: eval v4, eval v5, record v6 videos, tracking demo, singularity test
# Video recording: VS-Record-Play (manual viewport render + wrist TiledCamera).

set -euo pipefail

ISAACLAB=/home/krz/isaaclab_ws/IsaacLab
SCRIPTS=/home/krz/isaaclab_ws/scripts
OUT=/home/krz/isaaclab_ws/outputs/videos
mkdir -p "$OUT"

V4_CKPT="$ISAACLAB/logs/skrl/reach_franka_sac/2026-06-02_10-41-01_sac_torch/checkpoints/best_agent.pt"
V5_CKPT="$ISAACLAB/logs/skrl/reach_franka_sac/2026-06-02_14-05-00_sac_torch/checkpoints/best_agent.pt"
V6_CKPT="$ISAACLAB/logs/skrl/reach_franka_sac/2026-06-02_17-51-20_sac_torch/checkpoints/best_agent.pt"
V6_VID_DIR="$ISAACLAB/logs/skrl/reach_franka_sac/2026-06-02_17-51-20_sac_torch/videos/play_vs"
RECORD_TASK="Isaac-Reach-Franka-VS-Record-Play-v0"

run_isaac() {
    local desc="$1"; shift
    echo ""
    echo "============================================================"
    echo "  $desc"
    echo "============================================================"
    cd "$ISAACLAB"
    OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab --no-capture-output \
        python "$@"
    echo "[DONE] $desc"
}

# ── STEP 1: Eval v4 ─────────────────────────────────────────────────────────
run_isaac "VS v4 Eval (20 ep)" \
    "$SCRIPTS/play_vs.py" \
    --task Isaac-Reach-Franka-VS-NoCmd-Play-v0 \
    --checkpoint "$V4_CKPT" \
    --num_envs 1 --headless --num_episodes 20 \
    --no_video --algorithm SAC

# ── STEP 2: Eval v5 ─────────────────────────────────────────────────────────
run_isaac "VS v5 Eval (20 ep)" \
    "$SCRIPTS/play_vs.py" \
    --task Isaac-Reach-Franka-VS-NoCmd-Play-v0 \
    --checkpoint "$V5_CKPT" \
    --num_envs 1 --headless --num_episodes 20 \
    --no_video --algorithm SAC

# ── STEP 3: Record v6 perspective + wrist + composite ────────────────────────
run_isaac "VS v6 Video (10 ep)" \
    "$SCRIPTS/play_vs.py" \
    --task "$RECORD_TASK" \
    --checkpoint "$V6_CKPT" \
    --num_envs 1 --headless --num_episodes 10 \
    --algorithm SAC \
    --hold_pos_threshold 0.025 --hold_image_threshold 0.03

mkdir -p "$V6_VID_DIR"
for f in perspective wrist_cam composite; do
    src="$V6_VID_DIR/${f}.mp4"
    if [ -f "$src" ] && [ -s "$src" ]; then
        dst="$OUT/vs6_${f}.mp4"
        cp "$src" "$dst"
        echo "[INFO] Copied: $dst  ($(du -h "$src" | cut -f1))"
    else
        echo "[WARN] Missing or empty: $src"
    fi
done

# ── STEP 4: Tracking demo ────────────────────────────────────────────────────
TS=$(date +%Y%m%d_%H%M%S)
TRACK_OUT="$OUT/tracking_demo_vs6_${TS}.mp4"
run_isaac "VS v6 Tracking Demo" \
    "$SCRIPTS/play_tracking_demo.py" \
    --task "$RECORD_TASK" \
    --checkpoint "$V6_CKPT" \
    --num_envs 1 --headless \
    --algorithm SAC --total_steps 600 --traj_freq 120 \
    --hold_pos_threshold 0.025 --hold_image_threshold 0.03 \
    --out_video "$TRACK_OUT"

# ── STEP 5: Singularity test ─────────────────────────────────────────────────
SING_OUT="$OUT/singularity_test_vs6_annotated.mp4"
run_isaac "VS v6 Singularity Test" \
    "$SCRIPTS/play_singularity_test.py" \
    --task "$RECORD_TASK" \
    --checkpoint "$V6_CKPT" \
    --num_envs 1 --headless --num_episodes 10 \
    --algorithm SAC \
    --hold_pos_threshold 0.025 --hold_image_threshold 0.03 \
    --settle_steps 15 --singularity_scale 1.0 \
    --out_video "$SING_OUT"

# ── Verify videos ────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Verifying recorded videos"
echo "============================================================"
VERIFY_LIST=("$OUT/vs6_perspective.mp4" "$OUT/vs6_composite.mp4" "$TRACK_OUT" "$SING_OUT")
conda run -n env_isaaclab python "$SCRIPTS/verify_video_frames.py" --check-markers "${VERIFY_LIST[@]}"

# Wrist cam: lower std threshold (close-up view has less pixel variance)
conda run -n env_isaaclab python "$SCRIPTS/verify_video_frames.py" \
    --min-std 5 --min-unique 100 "$OUT/vs6_wrist_cam.mp4"

echo ""
echo "============================================================"
echo "  All tasks completed!"
ls -lh "$OUT"/vs6_*.mp4 "$OUT"/tracking_demo_vs6*.mp4 "$OUT"/singularity_test_vs6*.mp4 2>/dev/null || true
echo "============================================================"
