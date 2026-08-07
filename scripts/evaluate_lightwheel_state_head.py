#!/usr/bin/env python3
"""Evaluate the Lightwheel state-head on every frame of one held-out demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np
import torch

from ikea_model_rollout import ActionHead, project_action


GROUPS = {
    "grippers": (0, 2),
    "wrists": (2, 16),
    "navigation": (16, 19),
    "base_height": (19, 20),
    "torso_rpy": (20, 23),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--hdf5", type=Path, required=True)
    parser.add_argument("--demo", default="demo_1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(args.checkpoint, map_location=device, weights_only=False)
    state_mean = np.asarray(checkpoint["state_mean"], dtype=np.float32)
    state_std = np.asarray(checkpoint["state_std"], dtype=np.float32)
    action_mean = np.asarray(checkpoint["action_mean"], dtype=np.float32)
    action_std = np.asarray(checkpoint["action_std"], dtype=np.float32)
    first_weight = checkpoint["model_state_dict"]["model.0.weight"]
    second_weight = checkpoint["model_state_dict"]["model.2.weight"]
    model = ActionHead(int(state_mean.shape[0]), int(first_weight.shape[0]), int(second_weight.shape[0])).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    with h5py.File(args.hdf5, "r") as handle:
        demo = handle[f"data/{args.demo}"]
        state = np.concatenate(
            [
                np.asarray(demo["states/articulation/robot/root_pose"], dtype=np.float32),
                np.asarray(demo["states/articulation/robot/root_velocity"], dtype=np.float32),
                np.asarray(demo["states/articulation/robot/joint_position"], dtype=np.float32),
                np.asarray(demo["states/articulation/robot/joint_velocity"], dtype=np.float32),
            ],
            axis=1,
        )
        expert = np.asarray(demo["actions"], dtype=np.float32)
    if state.shape[1] != state_mean.shape[0] or expert.shape[1] != 23:
        raise RuntimeError(f"unexpected shapes state={state.shape} action={expert.shape}")

    with torch.no_grad():
        x = torch.from_numpy((state - state_mean) / state_std).to(device)
        normalized = model(x)
        raw = (normalized * torch.from_numpy(action_std).to(device) + torch.from_numpy(action_mean).to(device)).cpu().numpy()
    projected = np.stack([project_action(row) for row in raw])

    result = {
        "checkpoint": str(args.checkpoint),
        "hdf5": str(args.hdf5),
        "demo": args.demo,
        "frames": int(expert.shape[0]),
        "device": str(device),
        "raw_action_metrics": {},
        "projected_action_metrics": {},
        "first_raw_gripper_out_of_range": next((int(i) for i, row in enumerate(raw) if np.any((row[:2] < -1) | (row[:2] > 1))), None),
        "raw_action_max_abs": np.max(np.abs(raw), axis=0).astype(float).tolist(),
        "projected_action_max_abs": np.max(np.abs(projected), axis=0).astype(float).tolist(),
    }
    for name, (start, end) in GROUPS.items():
        for label, prediction in (("raw", raw), ("projected", projected)):
            delta = prediction[:, start:end] - expert[:, start:end]
            result[f"{label}_action_metrics"][name] = {
                "mae": float(np.mean(np.abs(delta))),
                "rmse": float(np.sqrt(np.mean(delta * delta))),
                "max_abs": float(np.max(np.abs(delta))),
            }
    result["first_frame_max_action_error"] = {
        "raw": int(np.argmax(np.max(np.abs(raw - expert), axis=1))),
        "projected": int(np.argmax(np.max(np.abs(projected - expert), axis=1))),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
