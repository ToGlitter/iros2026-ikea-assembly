#!/usr/bin/env python3
"""Train a small state-only BC model as an official-data pipeline smoke test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
import pyarrow.parquet as pq
import torch
from torch import nn


OBSERVATION_FIELDS = (
    "observation.state.ee_state",
    "observation.state.hand_state",
    "observation.state.robot_q_current",
)
ACTION_FIELDS = (
    "action.ee_action",
    "action.hand_cmd",
    "action.robot_q_desired",
)
TASK_COUNT = 8


def vectors(table: object, fields: tuple[str, ...]) -> np.ndarray:
    arrays = [
        np.asarray(table[field].combine_chunks().to_pylist(), dtype=np.float32)
        for field in fields
    ]
    return np.concatenate(arrays, axis=1)


def field_metrics(
    prediction: torch.Tensor, target: torch.Tensor
) -> dict[str, dict[str, float]]:
    metrics = {}
    offset = 0
    for field, size in zip(ACTION_FIELDS, (12, 2, 36)):
        delta = prediction[:, offset : offset + size] - target[:, offset : offset + size]
        metrics[field] = {
            "mae": float(delta.abs().mean().item()),
            "rmse": float(delta.square().mean().sqrt().item()),
        }
        offset += size
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-file", type=Path, required=True)
    parser.add_argument("--episode-index", type=int, default=159)
    parser.add_argument("--max-frames", type=int, default=2048)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    torch.manual_seed(0)
    np.random.seed(0)
    columns = ["episode_index", "task_index", *OBSERVATION_FIELDS, *ACTION_FIELDS]
    table = pq.read_table(args.data_file, columns=columns)
    episodes = np.asarray(table["episode_index"].combine_chunks().to_numpy())
    selected = np.flatnonzero(episodes == args.episode_index)[: args.max_frames]
    if selected.size < 32:
        raise ValueError(f"not enough frames for episode {args.episode_index}")
    table = table.take(selected)

    observation = vectors(table, OBSERVATION_FIELDS)
    task_index = np.asarray(table["task_index"].combine_chunks().to_numpy(), dtype=np.int64)
    task_one_hot = np.eye(TASK_COUNT, dtype=np.float32)[task_index]
    model_input = np.concatenate([observation, task_one_hot], axis=1)
    target = vectors(table, ACTION_FIELDS)

    permutation = np.random.permutation(selected.size)
    validation_size = max(1, selected.size // 10)
    validation_indices = permutation[:validation_size]
    training_indices = permutation[validation_size:]
    input_mean = model_input[training_indices].mean(axis=0)
    input_std = np.maximum(model_input[training_indices].std(axis=0), 1e-6)
    target_mean = target[training_indices].mean(axis=0)
    target_std = np.maximum(target[training_indices].std(axis=0), 1e-6)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    x = torch.from_numpy((model_input - input_mean) / input_std).to(device)
    y = torch.from_numpy((target - target_mean) / target_std).to(device)
    target_tensor = torch.from_numpy(target).to(device)
    train_ids = torch.from_numpy(training_indices).to(device)
    validation_ids = torch.from_numpy(validation_indices).to(device)
    model = nn.Sequential(
        nn.Linear(x.shape[1], 256),
        nn.GELU(),
        nn.Linear(256, 256),
        nn.GELU(),
        nn.Linear(256, y.shape[1]),
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)

    with torch.no_grad():
        initial_loss = float(nn.functional.mse_loss(model(x[train_ids]), y[train_ids]).item())
    started = time.perf_counter()
    loss_history = []
    model.train()
    for step in range(args.steps):
        batch = train_ids[
            torch.randint(0, train_ids.numel(), (args.batch_size,), device=device)
        ]
        prediction = model(x[batch])
        loss = nn.functional.mse_loss(prediction, y[batch])
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if step == 0 or (step + 1) % 50 == 0:
            loss_history.append({"step": step + 1, "normalized_mse": float(loss.item())})

    model.eval()
    target_mean_tensor = torch.from_numpy(target_mean).to(device)
    target_std_tensor = torch.from_numpy(target_std).to(device)
    with torch.no_grad():
        train_normalized = model(x[train_ids])
        validation_normalized = model(x[validation_ids])
        final_train_loss = float(
            nn.functional.mse_loss(train_normalized, y[train_ids]).item()
        )
        validation_loss = float(
            nn.functional.mse_loss(validation_normalized, y[validation_ids]).item()
        )
        train_prediction = train_normalized * target_std_tensor + target_mean_tensor
        validation_prediction = (
            validation_normalized * target_std_tensor + target_mean_tensor
        )

    checkpoint = {
        "model_state_dict": model.state_dict(),
        "input_mean": input_mean,
        "input_std": input_std,
        "target_mean": target_mean,
        "target_std": target_std,
        "observation_fields": OBSERVATION_FIELDS,
        "action_fields": ACTION_FIELDS,
        "task_count": TASK_COUNT,
    }
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(checkpoint, args.checkpoint)
    report = {
        "source": "BitRobot/G1_WBT_Dex1_Building-Children-Table",
        "baseline": "state-only MLP behavior-cloning pipeline smoke test",
        "episode_index": args.episode_index,
        "frames": int(selected.size),
        "training_frames": int(training_indices.size),
        "validation_frames": int(validation_indices.size),
        "input_dimension": int(x.shape[1]),
        "target_dimension": int(y.shape[1]),
        "device": str(device),
        "steps": args.steps,
        "elapsed_seconds": time.perf_counter() - started,
        "initial_normalized_mse": initial_loss,
        "final_train_normalized_mse": final_train_loss,
        "validation_normalized_mse": validation_loss,
        "loss_reduction_ratio": final_train_loss / initial_loss,
        "train_metrics": field_metrics(train_prediction, target_tensor[train_ids]),
        "validation_metrics": field_metrics(
            validation_prediction, target_tensor[validation_ids]
        ),
        "checkpoint": str(args.checkpoint),
        "scope": "Validates official data -> adapter -> optimizer -> checkpoint only; not an Isaac Sim policy.",
        "loss_history": loss_history,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
