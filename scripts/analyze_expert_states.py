#!/usr/bin/env python3
"""Locate meaningful motion segments in a RoboFinals HDF5 demonstration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np


def first_crossing(values: np.ndarray, threshold: float) -> int | None:
    hits = np.flatnonzero(values > threshold)
    return int(hits[0]) if hits.size else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("hdf5", type=Path)
    parser.add_argument("--demo", default="demo_0")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    with h5py.File(args.hdf5, "r") as handle:
        group = handle[f"data/{args.demo}"]
        states = group["states"]
        actions = np.asarray(group["actions"], dtype=np.float64)
        joints = np.asarray(
            states["articulation/robot/joint_position"], dtype=np.float64
        )
        rigid_objects = {
            name: np.asarray(value["root_pose"], dtype=np.float64)
            for name, value in states["rigid_object"].items()
        }

    joint_displacement = np.max(np.abs(joints - joints[0]), axis=1)
    right_fingers = joints[:, -2:]
    right_finger_displacement = np.max(
        np.abs(right_fingers - right_fingers[0]), axis=1
    )
    result: dict[str, Any] = {
        "demo": args.demo,
        "state_frames": int(joints.shape[0]),
        "action_frames": int(actions.shape[0]),
        "robot": {
            "first_joint_motion_over_0_01_rad": first_crossing(
                joint_displacement, 0.01
            ),
            "max_joint_displacement_rad": float(np.max(joint_displacement)),
            "max_joint_displacement_frame": int(np.argmax(joint_displacement)),
            "first_right_finger_motion_over_0_01_rad": first_crossing(
                right_finger_displacement, 0.01
            ),
            "max_right_finger_displacement_rad": float(
                np.max(right_finger_displacement)
            ),
            "max_right_finger_displacement_frame": int(
                np.argmax(right_finger_displacement)
            ),
        },
        "rigid_objects": {},
    }
    for name, poses in rigid_objects.items():
        displacement = np.linalg.norm(poses[:, :3] - poses[0, :3], axis=1)
        step_displacement = np.linalg.norm(np.diff(poses[:, :3], axis=0), axis=1)
        result["rigid_objects"][name] = {
            "first_motion_over_0_01_m": first_crossing(displacement, 0.01),
            "first_motion_over_0_03_m": first_crossing(displacement, 0.03),
            "max_displacement_m": float(np.max(displacement)),
            "max_displacement_frame": int(np.argmax(displacement)),
            "largest_step_m": float(np.max(step_displacement)),
            "largest_step_frame": int(np.argmax(step_displacement) + 1),
        }

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
