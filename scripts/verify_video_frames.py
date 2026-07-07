#!/usr/bin/env python3
"""Verify recorded MP4 files are not empty gray frames."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import numpy as np
from PIL import Image


def _extract_frame(video_path: str, frame_idx: int, out_png: str) -> bool:
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"select=eq(n\\,{frame_idx})",
        "-vframes", "1", out_png,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and os.path.isfile(out_png)


def _has_color_markers(arr: np.ndarray, min_sat_pixels: int = 200) -> bool:
    """Heuristic: colored debug markers vs flat gray scene."""
    if arr.ndim != 3 or arr.shape[2] < 3:
        return False
    rgb = arr[..., :3].astype(np.float32)
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    sat = mx - mn
    return int((sat > 40).sum()) >= min_sat_pixels


def _frame_stats(png_path: str) -> tuple[float, float, int]:
    arr = np.array(Image.open(png_path))
    if arr.ndim == 3:
        flat = arr.reshape(-1, arr.shape[-1])
        unique = len(np.unique(flat, axis=0))
    else:
        unique = len(np.unique(arr))
    return float(arr.mean()), float(arr.std()), unique


def verify_video(path: str, min_std: float = 25.0, min_unique: int = 1000,
                 min_size_kb: int = 100, frame_indices: list[int] | None = None,
                 check_markers: bool = False) -> list[str]:
    """Return list of error messages (empty if OK)."""
    errors: list[str] = []
    if not os.path.isfile(path):
        return [f"missing: {path}"]
    size_kb = os.path.getsize(path) / 1024
    if size_kb < min_size_kb:
        errors.append(f"too small ({size_kb:.1f} KB < {min_size_kb} KB)")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        errors.append(f"ffprobe failed: {probe.stderr.strip()[-200:]}")
        return errors

    indices = frame_indices or [50, 200]
    for idx in indices:
        tmp = f"/tmp/verify_frame_{os.getpid()}_{idx}.png"
        if not _extract_frame(path, idx, tmp):
            errors.append(f"cannot extract frame {idx}")
            continue
        arr = np.array(Image.open(tmp))
        mean, std, unique = float(arr.mean()), float(arr.std()), (
            len(np.unique(arr.reshape(-1, arr.shape[-1]), axis=0)) if arr.ndim == 3
            else len(np.unique(arr))
        )
        os.remove(tmp)
        if std < min_std:
            errors.append(f"frame {idx}: std={std:.1f} < {min_std} (likely gray)")
        if unique < min_unique:
            errors.append(f"frame {idx}: unique_colors={unique} < {min_unique}")
        if 180 <= mean <= 190 and std < 15:
            errors.append(f"frame {idx}: mean={mean:.1f} looks like uniform gray")
        if check_markers and not _has_color_markers(arr):
            errors.append(f"frame {idx}: no saturated color blobs (debug_vis markers?)")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Verify VS6 video quality")
    parser.add_argument("videos", nargs="+", help="MP4 paths to check")
    parser.add_argument("--min-std", type=float, default=25.0)
    parser.add_argument("--min-unique", type=int, default=1000)
    parser.add_argument("--min-size-kb", type=int, default=100)
    parser.add_argument("--check-markers", action="store_true",
                        help="Require colored pixels (goal/EE debug_vis markers)")
    args = parser.parse_args()

    failed = False
    for path in args.videos:
        errs = verify_video(
            path,
            min_std=args.min_std,
            min_unique=args.min_unique,
            min_size_kb=args.min_size_kb,
            check_markers=args.check_markers,
        )
        if errs:
            failed = True
            print(f"FAIL {path}:")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"OK   {path}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
