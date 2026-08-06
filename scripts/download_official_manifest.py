#!/usr/bin/env python3
"""Download the deduplicated files listed by plan_official_episodes.py."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


RESOLVE_ROOT = "https://huggingface.co/datasets/BitRobot/G1_WBT_Dex1_Building-Children-Table/resolve/main"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/official_lerobot"))
    parser.add_argument("--kind", choices=("all", "data", "rgb_video"), default="all")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    files = manifest["files"]
    if args.kind != "all":
        files = [item for item in files if item["kind"] == args.kind]
    total = len(files)
    for index, item in enumerate(files, start=1):
        relative_path = Path(item["path"])
        destination = args.dataset_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        url = f"{RESOLVE_ROOT}/{relative_path.as_posix()}"
        print(
            f"[{index}/{total}] {item['kind']} {relative_path} "
            f"(episodes={','.join(str(value) for value in item['episodes'])})",
            flush=True,
        )
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
                "--progress-bar",
                "--output",
                str(destination),
                url,
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
