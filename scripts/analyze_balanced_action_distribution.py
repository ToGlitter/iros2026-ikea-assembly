#!/usr/bin/env python3
"""Compare action statistics for a task-balanced anchor manifest and uniform sampling."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq


ACTION_FIELDS = (
    "action.ee_action",
    "action.hand_cmd",
    "action.robot_q_desired",
)
OBSERVATION_FIELDS = (
    "observation.state.ee_state",
    "observation.state.hand_state",
    "observation.state.robot_q_current",
)


def vectors(table: Any, fields: tuple[str, ...]) -> np.ndarray:
    return np.concatenate(
        [np.asarray(table[field].combine_chunks().to_pylist(), dtype=np.float32) for field in fields],
        axis=1,
    )


def summarize(array: np.ndarray) -> dict[str, Any]:
    return {
        "count": int(array.shape[0]),
        "mean": array.mean(axis=0).round(6).tolist() if array.size else [],
        "std": array.std(axis=0).round(6).tolist() if array.size else [],
        "min": array.min(axis=0).round(6).tolist() if array.size else [],
        "max": array.max(axis=0).round(6).tolist() if array.size else [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--anchor-manifest", type=Path, required=True)
    parser.add_argument("--episode-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--uniform-per-episode", type=int, default=256)
    args = parser.parse_args()

    anchors = json.loads(args.anchor_manifest.read_text(encoding="utf-8"))
    episode_manifest = json.loads(args.episode_manifest.read_text(encoding="utf-8"))
    requested = sorted({int(item["episode_index"]) for item in anchors["samples"]})
    anchor_keys = {(int(item["episode_index"]), int(item["frame_index"])): str(item["task"]) for item in anchors["samples"]}
    data_paths = sorted({str(item["data_path"]) for item in episode_manifest["episodes"] if int(item["episode_index"]) in requested})
    task_names = {
        int(row["task_index"]): str(row["__index_level_0__"])
        for row in pq.read_table(args.dataset_root / "meta/tasks.parquet").to_pylist()
    }
    balanced_rows: list[dict[str, Any]] = []
    uniform_rows: list[dict[str, Any]] = []
    table_cache: dict[str, Any] = {}
    for relative in data_paths:
        path = args.dataset_root / relative
        table = pq.read_table(path, columns=["episode_index", "frame_index", "task_index", *ACTION_FIELDS, *OBSERVATION_FIELDS])
        table_cache[relative] = table
        episode_values = np.asarray(table["episode_index"].combine_chunks().to_numpy(), dtype=np.int64)
        frame_values = np.asarray(table["frame_index"].combine_chunks().to_numpy(), dtype=np.int64)
        for episode_index in requested:
            rows = np.flatnonzero(episode_values == episode_index)
            if rows.size == 0:
                continue
            frame_to_row = {int(frame_values[row]): int(row) for row in rows}
            for frame_index in sorted(frame for episode, frame in anchor_keys if episode == episode_index):
                row = frame_to_row.get(frame_index)
                if row is None:
                    raise KeyError(f"anchor frame missing: episode={episode_index} frame={frame_index}")
                balanced_rows.append({"episode_index": episode_index, "frame_index": frame_index, "row": row, "table": table})
            count = min(args.uniform_per_episode, rows.size)
            for row in np.linspace(0, rows.size - 1, count, dtype=np.int64):
                actual = int(rows[row])
                uniform_rows.append({"episode_index": episode_index, "frame_index": int(frame_values[actual]), "row": actual, "table": table})

    def collect(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
        actions = np.concatenate([vectors(item["table"].take([item["row"]]), ACTION_FIELDS) for item in rows], axis=0)
        observations = np.concatenate([vectors(item["table"].take([item["row"]]), OBSERVATION_FIELDS) for item in rows], axis=0)
        counts: dict[str, int] = defaultdict(int)
        for item in rows:
            task_index = int(item["table"]["task_index"][item["row"]].as_py())
            counts[task_names.get(task_index, f"task_index_{task_index}")] += 1
        return actions, observations, dict(counts)

    balanced_actions, balanced_observations, balanced_counts = collect(balanced_rows)
    uniform_actions, uniform_observations, uniform_counts = collect(uniform_rows)
    report = {
        "source": "BitRobot/G1_WBT_Dex1_Building-Children-Table",
        "anchor_manifest": str(args.anchor_manifest),
        "episodes": requested,
        "balanced": {
            "task_counts": balanced_counts,
            "action": summarize(balanced_actions),
            "observation": summarize(balanced_observations),
        },
        "uniform": {
            "samples_per_episode": args.uniform_per_episode,
            "task_counts": uniform_counts,
            "action": summarize(uniform_actions),
            "observation": summarize(uniform_observations),
        },
        "interpretation": {
            "action_layout": "ee_action[12] + hand_cmd[2] + robot_q_desired[36]",
            "purpose": "sampling audit only; no training and no official-50D-to-Isaac-23D conversion",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"balanced_task_counts": balanced_counts, "uniform_task_counts": uniform_counts}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
