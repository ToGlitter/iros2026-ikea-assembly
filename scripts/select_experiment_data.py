#!/usr/bin/env python3
"""Select reproducible first-stage official and Lightwheel experiment data."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path


def evenly_spaced(values: list[int], count: int) -> list[int]:
    if count >= len(values):
        return list(values)
    positions = [round(i * (len(values) - 1) / (count - 1)) for i in range(count)]
    return [values[position] for position in positions]


def official_split(episode_ids: list[int]) -> dict[str, list[int]]:
    validation = [159, 300, 420, 532]
    test = [100, 250, 400, 500]
    reserved = set(validation + test)
    candidates = [episode for episode in episode_ids if episode not in reserved]
    required_train = [episode for episode in (155, 156, 157, 158) if episode in candidates]
    remainder = [episode for episode in candidates if episode not in required_train]
    train = required_train + evenly_spaced(remainder, 24 - len(required_train))
    return {"train": sorted(set(train)), "validation": validation, "test": test}


def lightwheel_split(files: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in files:
        groups[str(item.get("lfs_oid") or item.get("git_oid"))].append(item)
    representatives = [sorted(items, key=lambda item: item["path"])[0] for items in groups.values()]
    representatives.sort(key=lambda item: item["path"])
    forced_path = "data/AssembleTableTask_1784627181912351.hdf5"
    forced = next(item for item in representatives if item["path"] == forced_path)
    others = [item for item in representatives if item["path"] != forced_path]
    selected = [forced] + evenly_spaced(others, 15)
    selected = sorted({item["path"]: item for item in selected}.values(), key=lambda item: item["path"])
    train_paths = {item["path"] for item in selected if item["path"] != forced_path}
    train_paths = set(sorted(train_paths)[:11]) | {forced_path}
    remaining = [item for item in selected if item["path"] not in train_paths]
    return {
        "train": [item for item in selected if item["path"] in train_paths],
        "validation": remaining[:2],
        "test": remaining[2:4],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-metadata", type=Path, required=True)
    parser.add_argument("--lightwheel-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    official = json.loads(args.official_metadata.read_text(encoding="utf-8"))
    lightwheel = json.loads(args.lightwheel_manifest.read_text(encoding="utf-8"))
    official_ids = [int(item["episode_index"]) for item in official["episodes"]]
    official_splits = official_split(official_ids)
    lightwheel_splits = lightwheel_split(lightwheel["files"])
    report = {
        "official": {
            "repo_id": official["repo_id"],
            "requested_episode_count": 32,
            "splits": official_splits,
            "reason": "timeline-spaced selection with episodes 155-159 retained for local RGB validation and explicit holdout episodes",
        },
        "lightwheel": {
            "repo_id": lightwheel["repo_id"],
            "requested_file_count": 16,
            "unique_content_count_in_selection": len({item.get("lfs_oid") for group in lightwheel_splits.values() for item in group}),
            "splits": lightwheel_splits,
            "reason": "one representative per exact LFS content OID, spread across the remote manifest, with the locally verified demo retained",
        },
        "scope": "first-stage experiment selection only; no files are downloaded by this script",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "official_counts": {key: len(value) for key, value in official_splits.items()},
        "lightwheel_counts": {key: len(value) for key, value in lightwheel_splits.items()},
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
