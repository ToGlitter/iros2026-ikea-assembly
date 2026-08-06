#!/usr/bin/env python3
"""Build a deduplicated download manifest for selected official episodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


REPO_ID = "BitRobot/G1_WBT_Dex1_Building-Children-Table"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--episodes", type=int, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    info = json.loads((args.dataset_root / "meta/info.json").read_text())
    requested = sorted(set(args.episodes))
    rows: dict[int, tuple[dict[str, Any], Path]] = {}
    for metadata_path in sorted(args.dataset_root.glob("meta/episodes/**/*.parquet")):
        for row in pq.read_table(metadata_path).to_pylist():
            episode_index = int(row["episode_index"])
            if episode_index in requested:
                rows[episode_index] = (row, metadata_path)
    missing = sorted(set(requested) - set(rows))
    if missing:
        raise KeyError(f"episode metadata not found locally: {missing}")

    files: dict[str, dict[str, Any]] = {}
    episodes = []
    for episode_index in requested:
        row, metadata_path = rows[episode_index]
        data_path = info["data_path"].format(
            chunk_index=int(row["data/chunk_index"]),
            file_index=int(row["data/file_index"]),
        )
        files.setdefault(data_path, {"path": data_path, "kind": "data", "episodes": []})[
            "episodes"
        ].append(episode_index)
        videos = {}
        for feature, feature_info in sorted(info["features"].items()):
            if feature_info["dtype"] != "video" or feature.endswith("_ir"):
                continue
            prefix = f"videos/{feature}/"
            metadata = {
                key[len(prefix) :]: value
                for key, value in row.items()
                if key.startswith(prefix)
            }
            video_path = info["video_path"].format(
                video_key=feature,
                chunk_index=int(metadata["chunk_index"]),
                file_index=int(metadata["file_index"]),
            )
            files.setdefault(
                video_path,
                {"path": video_path, "kind": "rgb_video", "episodes": []},
            )["episodes"].append(episode_index)
            videos[feature] = {
                "path": video_path,
                "from_timestamp": float(metadata["from_timestamp"]),
                "to_timestamp": float(metadata["to_timestamp"]),
            }
        episodes.append(
            {
                "episode_index": episode_index,
                "length": int(row["length"]),
                "tasks": row["tasks"],
                "dataset_from_index": int(row["dataset_from_index"]),
                "dataset_to_index": int(row["dataset_to_index"]),
                "metadata_path": str(metadata_path),
                "data_path": data_path,
                "videos": videos,
            }
        )

    report = {
        "repo_id": REPO_ID,
        "dataset_format": info["codebase_version"],
        "fps": info["fps"],
        "episodes": episodes,
        "files": sorted(files.values(), key=lambda item: item["path"]),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
