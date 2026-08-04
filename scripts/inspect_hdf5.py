#!/usr/bin/env python3
"""Write a compact schema and action summary for a RoboFinals HDF5 demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np


def json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        return [json_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def summarize_dataset(dataset: h5py.Dataset) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "shape": list(dataset.shape),
        "dtype": str(dataset.dtype),
        "compression": dataset.compression,
        "chunks": list(dataset.chunks) if dataset.chunks else None,
        "attributes": {key: json_value(value) for key, value in dataset.attrs.items()},
    }

    name = dataset.name.lower()
    is_control_data = any(
        token in name
        for token in ("action", "eef", "gripper", "joint", "reward", "success")
    )
    if is_control_data and dataset.size and np.issubdtype(dataset.dtype, np.number):
        values = np.asarray(dataset[...])
        summary["statistics"] = {
            "min": float(np.nanmin(values)),
            "max": float(np.nanmax(values)),
            "mean": float(np.nanmean(values)),
        }
        if values.ndim >= 1:
            indices = sorted({0, values.shape[0] // 2, values.shape[0] - 1})
            summary["samples"] = {
                str(index): json_value(values[index]) for index in indices
            }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report: dict[str, Any] = {
        "file": str(args.input),
        "size_bytes": args.input.stat().st_size,
        "groups": {},
        "datasets": {},
    }
    with h5py.File(args.input, "r") as hdf5:
        report["attributes"] = {
            key: json_value(value) for key, value in hdf5.attrs.items()
        }

        def visit(name: str, obj: h5py.Group | h5py.Dataset) -> None:
            if isinstance(obj, h5py.Group):
                report["groups"][f"/{name}"] = {
                    "attributes": {
                        key: json_value(value) for key, value in obj.attrs.items()
                    }
                }
            else:
                report["datasets"][f"/{name}"] = summarize_dataset(obj)

        hdf5.visititems(visit)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
