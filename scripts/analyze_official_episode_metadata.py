#!/usr/bin/env python3
"""Audit all official episode metadata without loading frame Parquet files."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from statistics import mean, median
from typing import Any

import pyarrow.parquet as pq


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    info = json.loads((args.dataset_root / "meta/info.json").read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    source_files: dict[str, int] = {}
    for path in sorted((args.dataset_root / "meta/episodes").glob("**/*.parquet")):
        table = pq.read_table(path)
        source_files[str(path)] = table.num_rows
        rows.extend(table.to_pylist())
    rows.sort(key=lambda row: int(row["episode_index"]))

    episode_ids = [int(row["episode_index"]) for row in rows]
    lengths = [int(row["length"]) for row in rows]
    task_presence = Counter()
    task_sets = Counter()
    data_refs: dict[str, int] = defaultdict(int)
    video_refs: dict[str, Counter[str]] = defaultdict(Counter)
    episodes: list[dict[str, Any]] = []
    for row in rows:
        tasks = [str(task) for task in (row.get("tasks") or [])]
        task_presence.update(tasks)
        task_sets[tuple(tasks)] += 1
        data_path = info["data_path"].format(
            chunk_index=int(row["data/chunk_index"]), file_index=int(row["data/file_index"])
        )
        data_refs[data_path] += int(row["length"])
        videos: dict[str, Any] = {}
        for feature in sorted(info["features"]):
            if info["features"][feature]["dtype"] != "video":
                continue
            prefix = f"videos/{feature}/"
            metadata = {key[len(prefix):]: value for key, value in row.items() if key.startswith(prefix)}
            if not metadata:
                continue
            video_path = info["video_path"].format(
                video_key=feature,
                chunk_index=int(metadata["chunk_index"]),
                file_index=int(metadata["file_index"]),
            )
            video_refs[feature][video_path] += 1
            videos[feature] = {
                "path": video_path,
                "from_timestamp": float(metadata["from_timestamp"]),
                "to_timestamp": float(metadata["to_timestamp"]),
            }
        episodes.append(
            {
                "episode_index": int(row["episode_index"]),
                "length": int(row["length"]),
                "duration_seconds": round(int(row["length"]) / float(info["fps"]), 6),
                "tasks": tasks,
                "dataset_from_index": int(row["dataset_from_index"]),
                "dataset_to_index": int(row["dataset_to_index"]),
                "data_path": data_path,
                "videos": videos,
            }
        )

    expected_ids = list(range(int(info["total_episodes"])))
    missing_ids = sorted(set(expected_ids) - set(episode_ids))
    unexpected_ids = sorted(set(episode_ids) - set(expected_ids))
    contiguous = episode_ids == expected_ids
    report = {
        "repo_id": "BitRobot/G1_WBT_Dex1_Building-Children-Table",
        "scope": "all episode metadata Parquet files; frame data and video contents were not read",
        "dataset_info": {
            "codebase_version": info["codebase_version"],
            "fps": info["fps"],
            "claimed_total_episodes": info["total_episodes"],
            "claimed_total_frames": info["total_frames"],
            "total_tasks": info["total_tasks"],
        },
        "metadata_source_files": source_files,
        "episode_count": len(rows),
        "episode_index_range": [min(episode_ids), max(episode_ids)] if episode_ids else None,
        "episode_indices_contiguous_from_zero": contiguous,
        "missing_episode_indices": missing_ids,
        "unexpected_episode_indices": unexpected_ids,
        "frame_count_sum": sum(lengths),
        "frame_count_delta_vs_info": sum(lengths) - int(info["total_frames"]),
        "length_frames": {
            "min": min(lengths) if lengths else 0,
            "max": max(lengths) if lengths else 0,
            "mean": mean(lengths) if lengths else 0,
            "median": median(lengths) if lengths else 0,
        },
        "task_presence_episode_count": dict(task_presence),
        "unique_task_lists": {" | ".join(key): value for key, value in task_sets.items()},
        "data_file_count": len(data_refs),
        "data_file_frame_totals": dict(sorted(data_refs.items())),
        "video_file_count_by_feature": {feature: len(paths) for feature, paths in video_refs.items()},
        "video_file_reference_count_by_feature": {
            feature: dict(sorted(paths.items())) for feature, paths in video_refs.items()
        },
        "episodes": episodes,
        "interpretation": {
            "task_presence_warning": "episode metadata lists task vocabulary, not per-frame task durations",
            "next_frame_level_step": "download data Parquet files and run contiguous task_index analysis",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("episode_count", "frame_count_sum", "length_frames", "data_file_count", "video_file_count_by_feature")}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
