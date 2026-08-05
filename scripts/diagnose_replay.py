#!/usr/bin/env python3
"""Correlate replay trajectory errors with expert gripper action transitions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np


THRESHOLDS = {
    "robot_root_position_m": 0.05,
    "robot_root_orientation_rad": np.deg2rad(5.0),
    "robot_joint_max_abs_rad": 0.2,
}


def threshold_for(name: str) -> float | None:
    if name in THRESHOLDS:
        return float(THRESHOLDS[name])
    if name.endswith("_position_m"):
        return 0.03
    if name.endswith("_orientation_rad"):
        return float(np.deg2rad(10.0))
    return None


def transitions(
    values: np.ndarray, frame_limit: int
) -> list[dict[str, float | int]]:
    values = values[:frame_limit]
    indices = np.flatnonzero(np.diff(values) != 0.0) + 1
    return [
        {
            "frame_index": int(index),
            "from": float(values[index - 1]),
            "to": float(values[index]),
        }
        for index in indices
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("hdf5", type=Path)
    parser.add_argument("errors", type=Path)
    parser.add_argument("--demo", default="demo_0")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    with np.load(args.errors) as error_file:
        first_crossings = {}
        frames_in_error_trace = 0
        for name in error_file.files:
            frames_in_error_trace = max(frames_in_error_trace, len(error_file[name]))
            threshold = threshold_for(name)
            if threshold is None:
                continue
            values = error_file[name]
            hits = np.flatnonzero(values > threshold)
            first_crossings[name] = {
                "threshold": threshold,
                "frame_index": int(hits[0]) if hits.size else None,
                "max": float(np.max(values)),
            }

    with h5py.File(args.hdf5, "r") as handle:
        actions = np.asarray(handle[f"data/{args.demo}/actions"], dtype=np.float32)

    result = {
        "frames_in_error_trace": frames_in_error_trace,
        "first_threshold_crossings": first_crossings,
        "grippers": {
            "left": {
                "unique_values": np.unique(actions[:, 0]).astype(float).tolist(),
                "total_transition_count": int(
                    np.count_nonzero(np.diff(actions[:, 0]))
                ),
                "transitions_in_error_trace": transitions(
                    actions[:, 0], frames_in_error_trace
                ),
            },
            "right": {
                "unique_values": np.unique(actions[:, 1]).astype(float).tolist(),
                "total_transition_count": int(
                    np.count_nonzero(np.diff(actions[:, 1]))
                ),
                "transitions_in_error_trace": transitions(
                    actions[:, 1], frames_in_error_trace
                ),
            },
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
