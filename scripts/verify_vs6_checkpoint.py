#!/usr/bin/env python3
"""Verify a checkpoint is VS v6 (2026-06-02_17-51-20) without launching Isaac Sim."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

V6_RUN_ID = "2026-06-02_17-51-20"
V6_IE_WEIGHT = 0.5


def _grep_env_yaml(env_yaml: Path) -> dict:
    text = env_yaml.read_text()
    info: dict = {}
    info["has_pose_command"] = "pose_command" in text and "policy" in text
    info["has_image_error"] = bool(re.search(r"image_error:\s*\n", text))
    m = re.search(r"image_error_improvement:.*?weight:\s*([0-9.]+)", text, re.DOTALL)
    info["image_error_improvement_weight"] = float(m.group(1)) if m else None
    return info


def verify_vs6_checkpoint(checkpoint_path: str, strict: bool = True) -> dict:
    ckpt = Path(checkpoint_path).resolve()
    if not ckpt.is_file():
        raise FileNotFoundError(f"Checkpoint not found: {ckpt}")

    run_dir = ckpt.parent.parent
    env_yaml = run_dir / "params" / "env.yaml"
    if not env_yaml.is_file():
        raise FileNotFoundError(f"Missing params/env.yaml under {run_dir}")

    parsed = _grep_env_yaml(env_yaml)
    errors: list[str] = []
    info: dict = {
        "checkpoint": str(ckpt),
        "run_dir": str(run_dir),
        "run_id": run_dir.name,
    }

    if V6_RUN_ID not in run_dir.name:
        errors.append(f"run directory name should contain '{V6_RUN_ID}', got {run_dir.name}")

    if not parsed.get("has_pose_command"):
        errors.append("env.yaml should reference pose_command in policy obs")
    if not parsed.get("has_image_error"):
        errors.append("env.yaml should reference image_error obs term")

    weight = parsed.get("image_error_improvement_weight")
    info["image_error_improvement_weight"] = weight
    if weight != V6_IE_WEIGHT:
        errors.append(f"image_error_improvement.weight should be {V6_IE_WEIGHT}, got {weight}")

    try:
        import torch

        data = torch.load(ckpt, map_location="cpu", weights_only=False)
        state = data.get("policy", data)
        for key in ("net.0.weight",):
            if key in state:
                info["policy_in_features"] = int(state[key].shape[1])
                break
        if info.get("policy_in_features") not in (None, 39):
            errors.append(f"policy input dim expected 39 for VS v6, got {info.get('policy_in_features')}")
    except Exception as e:
        info["policy_dim_check"] = f"skipped ({e})"

    info["vs6_ok"] = len(errors) == 0
    info["errors"] = errors

    if strict and errors:
        raise ValueError("; ".join(errors))
    return info


def print_summary(info: dict):
    print(f"[VERIFY] Checkpoint : {info['checkpoint']}")
    print(f"[VERIFY] Run dir    : {info['run_dir']}")
    print(f"[VERIFY] VS v6 OK    : {info['vs6_ok']}")
    if info.get("image_error_improvement_weight") is not None:
        print(f"[VERIFY] image_error_improvement weight : {info['image_error_improvement_weight']}")
    if "policy_in_features" in info:
        print(f"[VERIFY] Policy input dim : {info['policy_in_features']}")
    if info.get("errors"):
        for e in info["errors"]:
            print(f"[VERIFY] WARN: {e}")


def main():
    parser = argparse.ArgumentParser(description="Verify VS v6 checkpoint")
    parser.add_argument("checkpoint", type=str, help="Path to best_agent.pt")
    parser.add_argument("--no-strict", action="store_true", help="Print warnings only, exit 0")
    args = parser.parse_args()
    try:
        info = verify_vs6_checkpoint(args.checkpoint, strict=not args.no_strict)
        print_summary(info)
        sys.exit(0 if info["vs6_ok"] else 1)
    except Exception as e:
        print(f"[VERIFY] FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
