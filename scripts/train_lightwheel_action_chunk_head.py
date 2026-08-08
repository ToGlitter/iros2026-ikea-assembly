#!/usr/bin/env python3
"""Train a short-history Lightwheel state policy that predicts action chunks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import h5py
import numpy as np
import torch
from torch import nn


STATE_FIELDS = (
    "states/articulation/robot/root_pose",
    "states/articulation/robot/root_velocity",
    "states/articulation/robot/joint_position",
    "states/articulation/robot/joint_velocity",
)
GROUPS = {
    "grippers": (0, 2),
    "wrists": (2, 16),
    "navigation": (16, 19),
    "base_height": (19, 20),
    "torso_rpy": (20, 23),
}


def state_window(state: np.ndarray, index: int, history: int) -> np.ndarray:
    start = max(0, index - history + 1)
    window = state[start : index + 1]
    if len(window) < history:
        window = np.concatenate(
            [np.repeat(window[:1], history - len(window), axis=0), window], axis=0
        )
    return window.reshape(-1)


def read_split(
    root: Path,
    files: list[dict],
    samples_per_demo: int,
    history: int,
    chunk_length: int,
    collect_deltas: bool = False,
) -> tuple[np.ndarray, np.ndarray, list[dict], np.ndarray | None]:
    states: list[np.ndarray] = []
    chunks: list[np.ndarray] = []
    demos: list[dict] = []
    deltas: list[np.ndarray] = []
    for item in files:
        path = root / item["path"]
        with h5py.File(path, "r") as hdf5:
            for name in sorted(n for n in hdf5["data"] if n.startswith("demo_")):
                demo = hdf5[f"data/{name}"]
                if not bool(demo.attrs.get("success", False)):
                    continue
                state = np.concatenate(
                    [np.asarray(demo[field], dtype=np.float32) for field in STATE_FIELDS],
                    axis=1,
                )
                action = np.asarray(demo["actions"], dtype=np.float32)
                available = len(action) - chunk_length + 1
                count = min(samples_per_demo, available)
                indices = np.linspace(0, available - 1, count, dtype=np.int64)
                states.append(
                    np.asarray(
                        [state_window(state, int(index), history) for index in indices],
                        dtype=np.float32,
                    )
                )
                chunks.append(
                    np.asarray(
                        [action[index : index + chunk_length] for index in indices],
                        dtype=np.float32,
                    )
                )
                if collect_deltas:
                    deltas.append(np.abs(np.diff(action, axis=0)))
                demos.append(
                    {
                        "path": str(path),
                        "demo": name,
                        "frame_count": len(action),
                        "sample_count": count,
                    }
                )
    if not states:
        raise RuntimeError("no successful demos found")
    delta_values = np.concatenate(deltas) if deltas else None
    return np.concatenate(states), np.concatenate(chunks), demos, delta_values


class ActionChunkHead(nn.Module):
    def __init__(self, state_dimension: int, chunk_length: int) -> None:
        super().__init__()
        self.model = nn.Sequential(
            nn.Linear(state_dimension, 512),
            nn.GELU(),
            nn.Linear(512, 512),
            nn.GELU(),
            nn.Linear(512, chunk_length * 23),
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.model(state)


def group_metrics(prediction: torch.Tensor, target: torch.Tensor) -> dict:
    result = {}
    for name, (start, end) in GROUPS.items():
        delta = prediction[..., start:end] - target[..., start:end]
        result[name] = {
            "mae": float(delta.abs().mean().item()),
            "rmse": float(delta.square().mean().sqrt().item()),
            "max_abs": float(delta.abs().max().item()),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history", type=int, default=4)
    parser.add_argument("--chunk-length", type=int, default=8)
    parser.add_argument("--samples-per-demo", type=int, default=512)
    parser.add_argument("--steps", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=256)
    args = parser.parse_args()
    if args.history < 1 or args.chunk_length < 1:
        parser.error("--history and --chunk-length must be positive")

    torch.manual_seed(0)
    np.random.seed(0)
    selection = json.loads(args.selection.read_text(encoding="utf-8"))["lightwheel"]["splits"]
    train_x, train_y, train_demos, train_deltas = read_split(
        args.dataset_root,
        selection["train"],
        args.samples_per_demo,
        args.history,
        args.chunk_length,
        collect_deltas=True,
    )
    validation_x, validation_y, validation_demos, _ = read_split(
        args.dataset_root,
        selection["validation"],
        args.samples_per_demo,
        args.history,
        args.chunk_length,
    )
    test_x, test_y, test_demos, _ = read_split(
        args.dataset_root,
        selection["test"],
        args.samples_per_demo,
        args.history,
        args.chunk_length,
    )
    state_mean = train_x.mean(axis=0)
    state_std = np.maximum(train_x.std(axis=0), 1e-6)
    action_mean = train_y.mean(axis=0)
    action_std = np.maximum(train_y.std(axis=0), 1e-6)
    action_delta_limit = np.quantile(train_deltas, 0.995, axis=0).astype(np.float32)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def states(values: np.ndarray) -> torch.Tensor:
        return torch.from_numpy(((values - state_mean) / state_std).astype(np.float32)).to(device)

    def actions(values: np.ndarray) -> torch.Tensor:
        normalized = (values - action_mean) / action_std
        return torch.from_numpy(normalized.reshape(len(values), -1).astype(np.float32)).to(device)

    train_x_t, validation_x_t, test_x_t = states(train_x), states(validation_x), states(test_x)
    train_y_t, validation_y_t, test_y_t = actions(train_y), actions(validation_y), actions(test_y)
    model = ActionChunkHead(train_x.shape[1], args.chunk_length).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    history_log = []
    started = time.perf_counter()
    for step in range(args.steps):
        batch = torch.randint(0, len(train_x_t), (args.batch_size,), device=device)
        loss = nn.functional.mse_loss(model(train_x_t[batch]), train_y_t[batch])
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if step == 0 or (step + 1) % 100 == 0:
            history_log.append({"step": step + 1, "normalized_mse": float(loss.detach())})

    mean_t = torch.from_numpy(action_mean.reshape(-1)).to(device)
    std_t = torch.from_numpy(action_std.reshape(-1)).to(device)
    model.eval()
    with torch.no_grad():
        predictions = {}
        for name, values in (
            ("train", train_x_t),
            ("validation", validation_x_t),
            ("test", test_x_t),
        ):
            predictions[name] = (model(values) * std_t + mean_t).reshape(
                -1, args.chunk_length, 23
            )
    targets = {
        "train": torch.from_numpy(train_y).to(device),
        "validation": torch.from_numpy(validation_y).to(device),
        "test": torch.from_numpy(test_y).to(device),
    }
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "state_mean": state_mean,
            "state_std": state_std,
            "action_mean": action_mean,
            "action_std": action_std,
            "action_delta_limit": action_delta_limit,
            "action_delta_quantile": 0.995,
            "state_fields": STATE_FIELDS,
            "history": args.history,
            "chunk_length": args.chunk_length,
            "action_groups": GROUPS,
        },
        args.checkpoint,
    )
    report = {
        "baseline": "four-frame proprioception to eight-step 23D action chunks",
        "history": args.history,
        "chunk_length": args.chunk_length,
        "device": str(device),
        "steps": args.steps,
        "elapsed_seconds": time.perf_counter() - started,
        "sample_counts": {
            "train": len(train_x),
            "validation": len(validation_x),
            "test": len(test_x),
        },
        "all_horizon_metrics": {
            name: group_metrics(predictions[name], targets[name]) for name in predictions
        },
        "first_step_metrics": {
            name: group_metrics(predictions[name][:, 0], targets[name][:, 0])
            for name in predictions
        },
        "action_delta_limit_p995": action_delta_limit.astype(float).tolist(),
        "train_demos": train_demos,
        "validation_demos": validation_demos,
        "test_demos": test_demos,
        "checkpoint": str(args.checkpoint),
        "loss_history": history_log,
        "scope": "supervised action-chunk prediction; closed-loop validation pending",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
