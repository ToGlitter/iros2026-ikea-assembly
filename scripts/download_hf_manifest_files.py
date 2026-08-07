#!/usr/bin/env python3
"""Download selected small files from a remote Hugging Face manifest.

This is intended for metadata (for example meta/episodes/*.parquet). It
verifies the downloaded byte count and, when present, the SHA-256 LFS OID.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import quote
from urllib.request import Request, urlopen


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download_item(item: dict, index: int, total: int, base_url: str, revision: str, dataset_root: Path) -> int:
    relative = Path(item["path"])
    destination = dataset_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected_size = int(item["size"])
    expected_hash = item.get("lfs_oid")
    if destination.exists() and destination.stat().st_size == expected_size:
        if not expected_hash or sha256(destination) == expected_hash:
            print(f"[{index}/{total}] cached {relative}", flush=True)
            return expected_size
    url = f"{base_url}/resolve/{quote(revision, safe='')}/{quote(item['path'], safe='/')}"
    print(f"[{index}/{total}] downloading {relative} ({expected_size} bytes)", flush=True)
    partial = destination.with_name(destination.name + ".part")
    if destination.exists() and destination.stat().st_size != expected_size and not partial.exists():
        # A prior connection may have produced a truncated destination.
        # Move it into the resumable path instead of deleting it.
        destination.replace(partial)
    for attempt in range(1, 11):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "iros2026-ikea-metadata-audit/1.0"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
            print(f"  {relative}: resuming at byte {offset} (attempt {attempt})", flush=True)
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=120) as response:
                resumed = bool(offset) and getattr(response, "status", 200) == 206
                if offset and not resumed:
                    print(f"  {relative}: server ignored Range; restarting", flush=True)
                    offset = 0
                mode = "ab" if resumed else "wb"
                with partial.open(mode) as handle:
                    while chunk := response.read(8 * 1024 * 1024):
                        handle.write(chunk)
        except Exception as exc:
            print(f"  {relative}: transfer error {exc}; retrying", flush=True)
        actual_size = partial.stat().st_size if partial.exists() else 0
        if actual_size == expected_size:
            break
        if actual_size > expected_size:
            raise RuntimeError(f"oversized partial for {relative}: {actual_size} > {expected_size}")
        if attempt < 10:
            time.sleep(min(10, attempt))
    else:
        raise RuntimeError(f"could not finish {relative} after 10 attempts")
    actual_size = partial.stat().st_size
    if actual_size != expected_size:
        raise RuntimeError(f"size mismatch for {relative}: {actual_size} != {expected_size}")
    partial.replace(destination)
    if expected_hash and sha256(destination) != expected_hash:
        raise RuntimeError(f"sha256 mismatch for {relative}")
    return actual_size


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    repo_id = manifest["repo_id"]
    revision = manifest.get("revision", "main")
    files = [item for item in manifest["files"] if item["path"].startswith(args.prefix)]
    base_url = f"https://huggingface.co/datasets/{quote(repo_id, safe='/')}"
    if args.workers < 1:
        raise ValueError("--workers must be positive")
    total_bytes = 0
    if args.workers == 1:
        for index, item in enumerate(files, start=1):
            total_bytes += download_item(item, index, len(files), base_url, revision, args.dataset_root)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(download_item, item, index, len(files), base_url, revision, args.dataset_root): item
                for index, item in enumerate(files, start=1)
            }
            for future in as_completed(futures):
                total_bytes += future.result()
    print(json.dumps({"downloaded_or_cached_files": len(files), "total_bytes": total_bytes}, indent=2))


if __name__ == "__main__":
    main()
