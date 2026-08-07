#!/usr/bin/env python3
"""Build a deterministic, task-balanced frame-anchor manifest.

The sampler selects evenly spaced frames within each task's complete set of
contiguous segments, then restores episode/frame order. It changes sampling
weights without destroying trajectory order for a downstream sequence loader.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("segments_report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples-per-task", type=int, default=1000)
    parser.add_argument("--episodes", type=int, nargs="+", help="Restrict sampling to these episode indices.")
    args = parser.parse_args()
    if args.samples_per_task <= 0:
        raise ValueError("--samples-per-task must be positive")

    report = json.loads(args.segments_report.read_text(encoding="utf-8"))
    episode_filter = set(args.episodes) if args.episodes else None
    by_task: dict[str, list[tuple[int, int, int, int]]] = defaultdict(list)
    for episode in report["episodes"]:
        episode_index = int(episode["episode_index"])
        if episode_filter is not None and episode_index not in episode_filter:
            continue
        for segment in episode["segments"]:
            task = str(segment["task"])
            by_task[task].append(
                (
                    episode_index,
                    int(segment["start_frame"]),
                    int(segment["end_frame"]),
                    int(segment["frame_count"]),
                )
            )

    samples: list[dict[str, int | str]] = []
    task_stats: dict[str, dict[str, int | float]] = {}
    for task, segments in sorted(by_task.items()):
        segments.sort(key=lambda item: (item[0], item[1]))
        total_frames = sum(item[3] for item in segments)
        target_count = min(args.samples_per_task, total_frames)
        ordinal_targets = np.linspace(0, total_frames - 1, target_count, dtype=np.int64)
        segment_cursor = 0
        segment_start_ordinal = 0
        for ordinal in ordinal_targets.tolist():
            while ordinal >= segment_start_ordinal + segments[segment_cursor][3]:
                segment_start_ordinal += segments[segment_cursor][3]
                segment_cursor += 1
            episode_index, start_frame, _, _ = segments[segment_cursor]
            frame_index = start_frame + int(ordinal - segment_start_ordinal)
            samples.append(
                {
                    "episode_index": episode_index,
                    "frame_index": frame_index,
                    "task": task,
                }
            )
        task_stats[task] = {
            "source_frames": total_frames,
            "source_segments": len(segments),
            "requested_samples": args.samples_per_task,
            "selected_samples": target_count,
            "source_fraction": total_frames / sum(
                value[3] for values in by_task.values() for value in values
            ),
            "selected_fraction": target_count / sum(
                min(args.samples_per_task, sum(value[3] for value in values))
                for values in by_task.values()
            ),
        }

    samples.sort(key=lambda item: (int(item["episode_index"]), int(item["frame_index"])))
    selected_counts = Counter(str(item["task"]) for item in samples)
    report_out = {
        "source": str(args.segments_report),
        "source_episode_indices": sorted(episode_filter) if episode_filter is not None else "all",
        "sampling": "evenly spaced within each task's global frame ordinal, then episode/frame sorted",
        "samples_per_task": args.samples_per_task,
        "total_selected_samples": len(samples),
        "selected_count_by_task": dict(selected_counts),
        "task_stats": task_stats,
        "samples": samples,
        "loader_note": "Use episode_index/frame_index to read state/action rows and timestamp; keep sorted order for sequence windows.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report_out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"total_selected_samples": len(samples), "selected_count_by_task": dict(selected_counts)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
