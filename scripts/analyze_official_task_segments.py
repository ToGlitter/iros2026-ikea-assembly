#!/usr/bin/env python3
"""Compute contiguous task-index intervals for selected official episodes."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq


def contiguous_segments(frame_indices: np.ndarray, task_indices: np.ndarray) -> list[dict[str, int]]:
    if frame_indices.size == 0:
        return []
    boundaries = np.flatnonzero(task_indices[1:] != task_indices[:-1]) + 1
    starts = np.concatenate(([0], boundaries))
    ends = np.concatenate((boundaries, [task_indices.size]))
    return [
        {
            "task_index": int(task_indices[start]),
            "start_frame": int(frame_indices[start]),
            "end_frame": int(frame_indices[end - 1]),
            "frame_count": int(end - start),
        }
        for start, end in zip(starts, ends)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    task_rows = pq.read_table(args.dataset_root / "meta/tasks.parquet").to_pylist()
    task_names = {
        int(row["task_index"]): str(row["__index_level_0__"])
        for row in task_rows
    }
    table_cache: dict[Path, Any] = {}
    episodes = []
    for episode in manifest["episodes"]:
        data_path = args.dataset_root / episode["data_path"]
        if data_path not in table_cache:
            table_cache[data_path] = pq.read_table(
                data_path, columns=["episode_index", "frame_index", "task_index"]
            )
        table = table_cache[data_path]
        all_episode_ids = np.asarray(table["episode_index"].combine_chunks().to_numpy())
        rows = np.flatnonzero(all_episode_ids == episode["episode_index"])
        frame_indices = np.asarray(
            table["frame_index"].combine_chunks().to_numpy(), dtype=np.int64
        )[rows]
        task_indices = np.asarray(
            table["task_index"].combine_chunks().to_numpy(), dtype=np.int64
        )[rows]
        order = np.argsort(frame_indices, kind="stable")
        frame_indices = frame_indices[order]
        task_indices = task_indices[order]
        segments = contiguous_segments(frame_indices, task_indices)
        for segment in segments:
            segment["task"] = task_names.get(segment["task_index"], "unknown")
        duration_by_task = Counter()
        segments_by_task = Counter()
        for segment in segments:
            task = segment["task"]
            duration_by_task[task] += segment["frame_count"]
            segments_by_task[task] += 1
        episodes.append(
            {
                "episode_index": episode["episode_index"],
                "length_from_manifest": episode["length"],
                "observed_frame_count": int(frame_indices.size),
                "segments": segments,
                "segment_count": len(segments),
                "duration_frames_by_task": dict(duration_by_task),
                "segment_count_by_task": dict(segments_by_task),
                "task_transition_sequence": [segment["task"] for segment in segments],
            }
        )

    aggregate_duration = Counter()
    aggregate_segments = Counter()
    for episode in episodes:
        aggregate_duration.update(episode["duration_frames_by_task"])
        aggregate_segments.update(episode["segment_count_by_task"])
    report = {
        "source": manifest["repo_id"],
        "episodes_requested": [episode["episode_index"] for episode in manifest["episodes"]],
        "task_names_by_index": task_names,
        "episode_count": len(episodes),
        "aggregate_duration_frames_by_task": dict(aggregate_duration),
        "aggregate_segment_count_by_task": dict(aggregate_segments),
        "episodes": episodes,
        "interpretation": {
            "unit": "contiguous runs of task_index in frame order",
            "warning": "task labels are annotations; their index order is not assumed to equal narrative skill order",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
