#!/usr/bin/env python3
"""Download only the RGB video files referenced by an inspected episode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


REPO_ID = "BitRobot/G1_WBT_Dex1_Building-Children-Table"
RESOLVE_ROOT = f"https://huggingface.co/datasets/{REPO_ID}/resolve/main"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("logs/official_lerobot_sample.json"),
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("datasets/official_lerobot"),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    episode = report["sample"]["episode_metadata"]
    videos = episode["videos"]
    rgb_videos = {
        feature: metadata
        for feature, metadata in videos.items()
        if not feature.endswith("_ir")
    }

    print(
        f"episode={episode['episode_index']} length={episode['length']} "
        f"rgb_files={len(rgb_videos)}"
    )
    for feature, metadata in sorted(rgb_videos.items()):
        chunk = int(metadata["chunk_index"])
        file_index = int(metadata["file_index"])
        relative_path = Path("videos") / feature / f"chunk-{chunk:03d}" / f"file-{file_index:03d}.mp4"
        destination = args.dataset_root / relative_path
        url = f"{RESOLVE_ROOT}/{relative_path.as_posix()}"
        print(
            f"{feature}: {metadata['from_timestamp']:.3f}-"
            f"{metadata['to_timestamp']:.3f}s -> {destination}"
        )
        if args.dry_run:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "curl",
                "--fail",
                "--location",
                "--continue-at",
                "-",
                "--retry",
                "10",
                "--retry-all-errors",
                "--output",
                str(destination),
                url,
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
