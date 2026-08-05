#!/usr/bin/env python3
"""Load a small state/action/image batch from the official LeRobot v3 data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import av
import numpy as np
from PIL import Image
import pyarrow.parquet as pq


VECTOR_COLUMNS = (
    "observation.state.ee_state",
    "observation.state.hand_state",
    "observation.state.robot_q_current",
    "action.ee_action",
    "action.hand_cmd",
    "action.robot_q_desired",
)


def find_episode_row(metadata_file: Path, episode_index: int) -> dict[str, Any]:
    for row in pq.read_table(metadata_file).to_pylist():
        if int(row["episode_index"]) == episode_index:
            return row
    raise KeyError(f"episode {episode_index} not found in {metadata_file}")


def video_metadata(row: dict[str, Any], feature: str) -> dict[str, Any]:
    prefix = f"videos/{feature}/"
    values = {
        key[len(prefix) :]: value
        for key, value in row.items()
        if key.startswith(prefix)
    }
    if not values:
        raise KeyError(f"video metadata not found for {feature}")
    return values


def decode_rgb_frame(path: Path, timestamp_s: float, fps: float) -> tuple[np.ndarray, float]:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        seek_s = max(0.0, timestamp_s - 2.0)
        seek_pts = int(seek_s / float(stream.time_base))
        container.seek(seek_pts, stream=stream, any_frame=False, backward=True)
        selected = None
        selected_time = None
        for frame in container.decode(stream):
            frame_time = float(frame.time)
            selected = frame
            selected_time = frame_time
            if frame_time >= timestamp_s - 0.5 / fps:
                break
        if selected is None or selected_time is None:
            raise RuntimeError(f"no frame decoded from {path} at {timestamp_s:.3f}s")
        return selected.to_ndarray(format="rgb24"), selected_time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--data-file", type=Path, required=True)
    parser.add_argument("--metadata-file", type=Path, required=True)
    parser.add_argument("--episode-index", type=int, default=159)
    parser.add_argument("--frames", type=int, nargs="+", default=[0, 4506, 9012])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    args = parser.parse_args()

    info = json.loads((args.dataset_root / "meta/info.json").read_text())
    fps = float(info["fps"])
    task_rows = pq.read_table(args.dataset_root / "meta/tasks.parquet").to_pylist()
    tasks = {
        int(row["task_index"]): str(row["__index_level_0__"])
        for row in task_rows
    }
    cameras = sorted(
        key
        for key, feature in info["features"].items()
        if feature["dtype"] == "video" and not key.endswith("_ir")
    )
    episode = find_episode_row(args.metadata_file, args.episode_index)
    columns = [
        "timestamp",
        "frame_index",
        "episode_index",
        "task_index",
        *VECTOR_COLUMNS,
    ]
    table = pq.read_table(args.data_file, columns=columns)
    rows_by_frame = {
        int(row["frame_index"]): row
        for row in table.to_pylist()
        if int(row["episode_index"]) == args.episode_index
        and int(row["frame_index"]) in args.frames
    }
    missing_frames = sorted(set(args.frames) - set(rows_by_frame))
    if missing_frames:
        raise KeyError(f"frames not found in data file: {missing_frames}")

    args.image_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    for frame_index in args.frames:
        row = rows_by_frame[frame_index]
        timestamp = float(row["timestamp"])
        images = {}
        for camera in cameras:
            metadata = video_metadata(episode, camera)
            relative_path = (
                Path("videos")
                / camera
                / f"chunk-{int(metadata['chunk_index']):03d}"
                / f"file-{int(metadata['file_index']):03d}.mp4"
            )
            video_path = args.dataset_root / relative_path
            target_time = float(metadata["from_timestamp"]) + timestamp
            image, decoded_time = decode_rgb_frame(video_path, target_time, fps)
            image_name = f"episode-{args.episode_index:03d}_frame-{frame_index:05d}_{camera.rsplit('.', 1)[-1]}.jpg"
            Image.fromarray(image).save(args.image_dir / image_name, quality=90)
            images[camera] = {
                "path": str(relative_path),
                "target_timestamp": target_time,
                "decoded_timestamp": decoded_time,
                "timestamp_error": decoded_time - target_time,
                "shape": list(image.shape),
                "mean": float(image.mean()),
                "std": float(image.std()),
                "saved_image": image_name,
            }
        samples.append(
            {
                "frame_index": frame_index,
                "timestamp": timestamp,
                "task_index": int(row["task_index"]),
                "task": tasks[int(row["task_index"])],
                "vectors": {
                    name: {
                        "shape": list(np.asarray(row[name]).shape),
                        "finite": bool(np.isfinite(row[name]).all()),
                    }
                    for name in VECTOR_COLUMNS
                },
                "images": images,
            }
        )

    report = {
        "source": "BitRobot/G1_WBT_Dex1_Building-Children-Table",
        "episode_index": args.episode_index,
        "dataset_format": info["codebase_version"],
        "fps": fps,
        "tasks": tasks,
        "samples": samples,
        "compatibility": {
            "container_lerobot_version": "0.1.0",
            "native_loader": "incompatible with this dataset's v3 Parquet metadata",
            "simulation_action_dimension": 23,
            "official_robot_action_dimension": 36,
            "ee_rotation_encoding": "not documented; do not convert to simulator quaternions yet",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
