#!/usr/bin/env python3
"""Build a lightweight manifest for locally available Lightwheel HDF5 demos."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import h5py


CAMERAS = (
    "first_person_camera_rgb",
    "left_hand_camera_rgb",
    "right_hand_camera_rgb",
)


def sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def decode_json(value: Any) -> Any:
    if isinstance(value, bytes):
        return json.loads(value.decode("utf-8"))
    if isinstance(value, str):
        return json.loads(value)
    return value


def inspect_file(path: Path, include_sha256: bool) -> dict[str, Any]:
    with h5py.File(path, "r") as hdf5:
        data = hdf5["data"]
        env_args = decode_json(data.attrs["env_args"])
        demos = []
        for name in sorted(key for key in data if key.startswith("demo_")):
            demo = data[name]
            action_shape = list(demo["actions"].shape)
            camera_shapes = {
                camera: list(demo[f"obs/{camera}"].shape)
                for camera in CAMERAS
                if f"obs/{camera}" in demo
            }
            demos.append(
                {
                    "demo": name,
                    "frame_count": int(demo.attrs.get("num_samples", action_shape[0])),
                    "success": bool(demo.attrs.get("success", False)),
                    "action_shape": action_shape,
                    "camera_shapes": camera_shapes,
                    "has_states": "states" in demo,
                    "has_initial_state": "initial_state" in demo,
                    "checkpoint_count": int(demo["checkpoints/frame_index"].shape[0])
                    if "checkpoints/frame_index" in demo
                    else 0,
                }
            )
        sim_args = env_args.get("sim_args", {})
        dt = sim_args.get("dt")
        decimation = sim_args.get("decimation")
        result = {
            "path": str(path),
            "file_size_bytes": path.stat().st_size,
            "sha256": sha256(path) if include_sha256 else None,
            "demo_count": len(demos),
            "demos": demos,
            "task_name": env_args.get("task_name"),
            "language": env_args.get("lang"),
            "robot_name": env_args.get("robot_name"),
            "camera_names": list(CAMERAS),
            "simulation_dt": dt,
            "decimation": decimation,
            "control_hz": 1.0 / (float(dt) * int(decimation)) if dt and decimation else None,
            "success_condition": env_args.get("success_condition"),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sha256", action="store_true")
    args = parser.parse_args()

    files = sorted(args.dataset_dir.glob("AssembleTableTask_*.hdf5"))
    report = {
        "dataset_dir": str(args.dataset_dir),
        "local_file_count": len(files),
        "files": [inspect_file(path, args.sha256) for path in files],
        "scope": "local manifest only; absence of files does not imply the remote Lightwheel dataset has fewer demos",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
