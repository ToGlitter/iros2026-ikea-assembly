#!/usr/bin/env python3
"""Inspect a minimal slice of the official BitRobot LeRobot dataset."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq


VECTOR_COLUMNS = (
    "observation.state.ee_state",
    "observation.state.hand_state",
    "observation.state.robot_q_current",
    "action.ee_action",
    "action.hand_cmd",
    "action.robot_q_desired",
)

EPISODE_FIELDS = (
    "episode_index",
    "tasks",
    "length",
    "data/chunk_index",
    "data/file_index",
    "dataset_from_index",
    "dataset_to_index",
)


def json_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def scalar_values(table: Any, name: str) -> np.ndarray:
    return np.asarray(table[name].combine_chunks().to_numpy())


def vector_values(table: Any, name: str) -> np.ndarray:
    return np.asarray(table[name].combine_chunks().to_pylist(), dtype=np.float32)


def vector_summary(values: np.ndarray) -> dict[str, Any]:
    return {
        "shape": list(values.shape),
        "finite": bool(np.isfinite(values).all()),
        "min": np.min(values, axis=0).tolist(),
        "max": np.max(values, axis=0).tolist(),
        "mean": np.mean(values, axis=0).tolist(),
        "first": values[0].tolist(),
        "last": values[-1].tolist(),
    }


def compact_episode_metadata(row: dict[str, Any], metadata_path: Path) -> dict[str, Any]:
    metadata = {key: row[key] for key in EPISODE_FIELDS if key in row}
    videos: dict[str, dict[str, Any]] = {}
    prefix = "videos/"
    for key, value in row.items():
        if not key.startswith(prefix):
            continue
        feature, field = key[len(prefix) :].rsplit("/", 1)
        videos.setdefault(feature, {})[field] = value
    metadata["videos"] = videos
    metadata["metadata_path"] = str(metadata_path)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--data-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    info_path = args.dataset_root / "meta/info.json"
    tasks_path = args.dataset_root / "meta/tasks.parquet"
    info = json.loads(info_path.read_text(encoding="utf-8"))
    task_rows = pq.read_table(tasks_path).to_pylist()

    parquet_file = pq.ParquetFile(args.data_file)
    schema_names = parquet_file.schema_arrow.names
    columns = [
        "timestamp",
        "frame_index",
        "episode_index",
        "index",
        "task_index",
        *VECTOR_COLUMNS,
    ]
    missing = sorted(set(columns) - set(schema_names))
    if missing:
        raise KeyError(f"missing expected columns: {missing}")

    table = parquet_file.read(columns=columns)
    episodes = scalar_values(table, "episode_index").astype(np.int64)
    tasks = scalar_values(table, "task_index").astype(np.int64)
    frames = scalar_values(table, "frame_index").astype(np.int64)
    timestamps = scalar_values(table, "timestamp").astype(np.float64)
    unique_episodes = np.unique(episodes)
    episode_metadata = None
    metadata_files = []
    if unique_episodes.size == 1:
        episode_index = int(unique_episodes[0])
        for metadata_path in sorted(
            args.dataset_root.glob("meta/episodes/**/*.parquet")
        ):
            metadata_rows = pq.read_table(metadata_path).to_pylist()
            metadata_indices = [int(row["episode_index"]) for row in metadata_rows]
            metadata_files.append(
                {
                    "path": str(metadata_path),
                    "row_count": len(metadata_rows),
                    "episode_index_range": [
                        min(metadata_indices),
                        max(metadata_indices),
                    ],
                }
            )
            for row in metadata_rows:
                if int(row["episode_index"]) == episode_index:
                    episode_metadata = compact_episode_metadata(row, metadata_path)
                    break
            if episode_metadata is not None:
                break

    report = {
        "source": "BitRobot/G1_WBT_Dex1_Building-Children-Table",
        "codebase_version": info["codebase_version"],
        "robot_type": info["robot_type"],
        "dataset": {
            "total_episodes": info["total_episodes"],
            "total_frames": info["total_frames"],
            "total_tasks": info["total_tasks"],
            "fps": info["fps"],
        },
        "tasks": task_rows,
        "sample": {
            "path": str(args.data_file),
            "file_size_bytes": args.data_file.stat().st_size,
            "row_count": table.num_rows,
            "row_group_count": parquet_file.num_row_groups,
            "schema": str(parquet_file.schema_arrow),
            "episode_counts": {
                str(key): value
                for key, value in sorted(Counter(episodes.tolist()).items())
            },
            "task_counts": {
                str(key): value
                for key, value in sorted(Counter(tasks.tolist()).items())
            },
            "episode_metadata": episode_metadata,
            "metadata_files": metadata_files,
            "frame_index_range": [int(frames.min()), int(frames.max())],
            "timestamp_range": [float(timestamps.min()), float(timestamps.max())],
            "vectors": {
                name: vector_summary(vector_values(table, name))
                for name in VECTOR_COLUMNS
            },
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_value(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(json_value(report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
