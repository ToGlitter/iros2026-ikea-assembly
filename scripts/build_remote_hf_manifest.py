#!/usr/bin/env python3
"""Build a metadata-only manifest from a Hugging Face dataset tree.

The tree API is paginated with an opaque cursor carried in the HTTP Link
header. This script follows that cursor and never downloads file contents.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


LINK_NEXT = re.compile(r"<([^>]+)>;\s*rel=\"next\"")


def fetch_page(url: str, retries: int = 5) -> tuple[list[dict[str, Any]], str | None]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = Request(url, headers={"User-Agent": "iros2026-ikea-metadata-audit/1.0"})
            with urlopen(request, timeout=60) as response:
                payload = json.load(response)
                link = response.headers.get("Link", "")
            next_url = LINK_NEXT.search(link)
            return payload, next_url.group(1) if next_url else None
        except Exception as exc:  # pragma: no cover - network failures are environment-specific
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error


def list_tree(repo_id: str, revision: str, path: str, recursive: bool, limit: int) -> list[dict[str, Any]]:
    encoded_repo = quote(repo_id, safe="/")
    encoded_revision = quote(revision, safe="")
    encoded_path = quote(path.strip("/"), safe="/")
    url = (
        f"https://huggingface.co/api/datasets/{encoded_repo}/tree/{encoded_revision}"
        f"/{encoded_path}?recursive={'true' if recursive else 'false'}&limit={limit}"
    )
    entries: list[dict[str, Any]] = []
    page = 0
    while url:
        page += 1
        payload, url = fetch_page(url)
        if not isinstance(payload, list):
            raise ValueError(f"unexpected tree payload on page {page}: {type(payload)!r}")
        entries.extend(payload)
        print(f"  {repo_id}:{path or '/'} page {page}, {len(entries)} entries", flush=True)
    return entries


def summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    files = [entry for entry in entries if entry.get("type") == "file"]
    sizes = [int(entry.get("lfs", {}).get("size", entry.get("size", 0))) for entry in files]
    by_oid: dict[str, list[str]] = defaultdict(list)
    for entry in files:
        oid = entry.get("lfs", {}).get("oid") or entry.get("oid")
        if oid:
            by_oid[str(oid)].append(str(entry["path"]))
    duplicate_groups = [paths for paths in by_oid.values() if len(paths) > 1]
    return {
        "file_count": len(files),
        "directory_count": sum(entry.get("type") == "directory" for entry in entries),
        "total_logical_bytes": sum(sizes),
        "min_file_bytes": min(sizes) if sizes else 0,
        "max_file_bytes": max(sizes) if sizes else 0,
        "mean_file_bytes": statistics.mean(sizes) if sizes else 0,
        "unique_content_count": len(by_oid),
        "duplicate_content_group_count": len(duplicate_groups),
        "duplicate_content_groups": duplicate_groups,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--path", default="")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    entries = list_tree(args.repo_id, args.revision, args.path, args.recursive, args.limit)
    report = {
        "repo_id": args.repo_id,
        "revision": args.revision,
        "path": args.path,
        "recursive": args.recursive,
        "scope": "remote Hugging Face tree metadata only; file contents were not downloaded",
        "summary": summarize(entries),
        "files": sorted(
            [
                {
                    "path": entry["path"],
                    "size": int(entry.get("lfs", {}).get("size", entry.get("size", 0))),
                    "git_oid": entry.get("oid"),
                    "lfs_oid": entry.get("lfs", {}).get("oid"),
                    "xet_hash": entry.get("xetHash"),
                }
                for entry in entries
                if entry.get("type") == "file"
            ],
            key=lambda item: item["path"],
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
