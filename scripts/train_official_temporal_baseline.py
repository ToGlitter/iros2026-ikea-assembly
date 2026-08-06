#!/usr/bin/env python3
"""Train a temporal four-camera BC model with action chunks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
import pyarrow.parquet as pq
import torch
from torch import nn

from train_official_visual_baseline import (
    ACTION_FIELDS,
    OBSERVATION_FIELDS,
    TASK_COUNT,
    decode_frames,
    table_vectors,
)


ACTION_SIZES = (12, 2, 36)
DEFAULT_HISTORY_OFFSETS = (-6, -4, -2, 0)


def build_cache(
    dataset_root: Path,
    manifest: dict,
    samples_per_episode: int,
    image_size: int,
    history_offsets: tuple[int, ...],
    action_chunk: int,
) -> dict[str, np.ndarray]:
    if not history_offsets or history_offsets[-1] != 0:
        raise ValueError("history offsets must be non-empty and end at zero")
    if tuple(sorted(set(history_offsets))) != history_offsets:
        raise ValueError("history offsets must be sorted and unique")
    if action_chunk < 1:
        raise ValueError("action chunk must be positive")

    table_cache: dict[Path, object] = {}
    images = []
    actions = []
    observations = []
    tasks = []
    episode_ids = []
    frame_ids = []
    max_timestamp_error = 0.0
    fps = float(manifest["fps"])

    for episode in manifest["episodes"]:
        data_path = dataset_root / episode["data_path"]
        if data_path not in table_cache:
            table_cache[data_path] = pq.read_table(
                data_path,
                columns=[
                    "episode_index",
                    "frame_index",
                    "timestamp",
                    "task_index",
                    *OBSERVATION_FIELDS,
                    *ACTION_FIELDS,
                ],
            )
        table = table_cache[data_path]
        all_episode_ids = np.asarray(table["episode_index"].combine_chunks().to_numpy())
        episode_rows = np.flatnonzero(all_episode_ids == episode["episode_index"])
        first_anchor = -history_offsets[0]
        last_anchor = episode_rows.size - action_chunk
        if last_anchor < first_anchor:
            raise ValueError(f"episode {episode['episode_index']} is too short")
        sample_count = min(samples_per_episode, last_anchor - first_anchor + 1)
        anchors = np.linspace(first_anchor, last_anchor, sample_count, dtype=np.int64)

        history_within = anchors[:, None] + np.asarray(history_offsets)[None, :]
        history_rows = episode_rows[history_within.reshape(-1)]
        selected_history = table.take(history_rows)
        history_timestamps = np.asarray(
            selected_history["timestamp"].combine_chunks().to_numpy(), dtype=np.float64
        ).reshape(sample_count, len(history_offsets))
        camera_images = []
        for _, metadata in sorted(episode["videos"].items()):
            targets = history_timestamps.reshape(-1) + float(metadata["from_timestamp"])
            decoded, timestamp_error = decode_frames(
                dataset_root / metadata["path"], targets, fps, image_size
            )
            camera_images.append(
                decoded.reshape(sample_count, len(history_offsets), image_size, image_size, 3)
            )
            max_timestamp_error = max(max_timestamp_error, timestamp_error)
        images.append(np.stack(camera_images, axis=2))

        observations.append(
            table_vectors(selected_history, OBSERVATION_FIELDS).reshape(
                sample_count, len(history_offsets), -1
            )
        )
        action_within = anchors[:, None] + np.arange(action_chunk)[None, :]
        selected_actions = table.take(episode_rows[action_within.reshape(-1)])
        actions.append(
            table_vectors(selected_actions, ACTION_FIELDS).reshape(
                sample_count, action_chunk, -1
            )
        )
        selected_anchors = table.take(episode_rows[anchors])
        tasks.append(
            np.asarray(
                selected_anchors["task_index"].combine_chunks().to_numpy(),
                dtype=np.int64,
            )
        )
        episode_ids.append(
            np.full(sample_count, episode["episode_index"], dtype=np.int64)
        )
        frame_ids.append(
            np.asarray(
                selected_anchors["frame_index"].combine_chunks().to_numpy(),
                dtype=np.int64,
            )
        )

    return {
        "images": np.concatenate(images),
        "observations": np.concatenate(observations),
        "actions": np.concatenate(actions),
        "tasks": np.concatenate(tasks),
        "episode_ids": np.concatenate(episode_ids),
        "frame_ids": np.concatenate(frame_ids),
        "history_offsets": np.asarray(history_offsets, dtype=np.int64),
        "action_chunk": np.asarray(action_chunk, dtype=np.int64),
        "samples_per_episode": np.asarray(samples_per_episode, dtype=np.int64),
        "image_size": np.asarray(image_size, dtype=np.int64),
        "max_timestamp_error": np.asarray(max_timestamp_error),
    }


def cache_matches(
    data: dict[str, np.ndarray],
    samples_per_episode: int,
    image_size: int,
    history_offsets: tuple[int, ...],
    action_chunk: int,
) -> bool:
    required = {
        "images",
        "observations",
        "actions",
        "tasks",
        "episode_ids",
        "frame_ids",
        "history_offsets",
        "action_chunk",
        "samples_per_episode",
        "image_size",
        "max_timestamp_error",
    }
    return required.issubset(data) and all(
        (
            np.array_equal(data["history_offsets"], np.asarray(history_offsets)),
            int(data["action_chunk"]) == action_chunk,
            int(data["samples_per_episode"]) == samples_per_episode,
            int(data["image_size"]) == image_size,
        )
    )


class TemporalVisualBC(nn.Module):
    def __init__(
        self,
        camera_count: int,
        state_dimension: int,
        action_dimension: int,
        action_chunk: int,
    ) -> None:
        super().__init__()
        self.camera_count = camera_count
        self.action_dimension = action_dimension
        self.action_chunk = action_chunk
        self.encoder = nn.Sequential(
            nn.Conv2d(3, 16, kernel_size=5, stride=2, padding=2),
            nn.GELU(),
            nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1),
            nn.GELU(),
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
            nn.GELU(),
            nn.AdaptiveAvgPool2d(1),
        )
        self.temporal = nn.GRU(
            camera_count * 64 + state_dimension + TASK_COUNT,
            256,
            batch_first=True,
        )
        self.head = nn.Sequential(
            nn.Linear(256, 256),
            nn.GELU(),
            nn.Linear(256, action_chunk * action_dimension),
        )

    def forward(
        self, images: torch.Tensor, state: torch.Tensor, tasks: torch.Tensor
    ) -> torch.Tensor:
        batch, history, cameras, channels, height, width = images.shape
        encoded = self.encoder(
            images.reshape(batch * history * cameras, channels, height, width)
        )
        encoded = encoded.reshape(batch, history, cameras * 64)
        repeated_tasks = tasks[:, None, :].expand(-1, history, -1)
        sequence = torch.cat([encoded, state, repeated_tasks], dim=2)
        _, hidden = self.temporal(sequence)
        return self.head(hidden[-1]).reshape(
            batch, self.action_chunk, self.action_dimension
        )


def field_metrics(
    prediction: torch.Tensor, target: torch.Tensor
) -> dict[str, dict[str, float]]:
    result = {}
    offset = 0
    for field, size in zip(ACTION_FIELDS, ACTION_SIZES):
        delta = prediction[..., offset : offset + size] - target[..., offset : offset + size]
        result[field] = {
            "mae": float(delta.abs().mean().item()),
            "rmse": float(delta.square().mean().sqrt().item()),
        }
        offset += size
    return result


def balanced_mse(prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    losses = []
    offset = 0
    for size in ACTION_SIZES:
        losses.append(
            nn.functional.mse_loss(
                prediction[..., offset : offset + size],
                target[..., offset : offset + size],
            )
        )
        offset += size
    return torch.stack(losses).mean()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples-per-episode", type=int, default=256)
    parser.add_argument("--image-size", type=int, default=64)
    parser.add_argument("--history-offsets", type=int, nargs="+", default=DEFAULT_HISTORY_OFFSETS)
    parser.add_argument("--action-chunk", type=int, default=8)
    parser.add_argument(
        "--target-mode",
        choices=("direct", "residual", "hybrid"),
        default="residual",
    )
    parser.add_argument("--validation-episode", type=int, default=159)
    parser.add_argument("--steps", type=int, default=3000)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--eval-batch-size", type=int, default=64)
    args = parser.parse_args()

    torch.manual_seed(0)
    np.random.seed(0)
    history_offsets = tuple(args.history_offsets)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    sample_data: dict[str, np.ndarray] = {}
    if args.cache.exists():
        with np.load(args.cache) as cached:
            sample_data = {key: cached[key] for key in cached.files}
    if not cache_matches(
        sample_data,
        args.samples_per_episode,
        args.image_size,
        history_offsets,
        args.action_chunk,
    ):
        sample_data = build_cache(
            args.dataset_root,
            manifest,
            args.samples_per_episode,
            args.image_size,
            history_offsets,
            args.action_chunk,
        )
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(args.cache, **sample_data)

    images = sample_data["images"]
    observations = sample_data["observations"].astype(np.float32)
    targets = sample_data["actions"].astype(np.float32)
    task_one_hot = np.eye(TASK_COUNT, dtype=np.float32)[sample_data["tasks"]]
    episode_ids = sample_data["episode_ids"]
    all_episodes = sorted(set(episode_ids.tolist()))
    if args.validation_episode not in all_episodes:
        raise ValueError(
            f"validation episode {args.validation_episode} is not in {all_episodes}"
        )
    train_indices = np.flatnonzero(episode_ids != args.validation_episode)
    validation_indices = np.flatnonzero(episode_ids == args.validation_episode)
    training_episodes = [
        episode for episode in all_episodes if episode != args.validation_episode
    ]

    latest_observations = observations[:, -1:, :]
    target_base = np.zeros_like(latest_observations)
    if args.target_mode == "residual":
        target_base = latest_observations
    elif args.target_mode == "hybrid":
        target_base[..., 12:] = latest_observations[..., 12:]
    training_targets = targets - target_base
    target_mean = training_targets[train_indices].mean(axis=(0, 1))
    target_std = np.maximum(training_targets[train_indices].std(axis=(0, 1)), 1e-6)
    observation_mean = observations[train_indices].mean(axis=(0, 1))
    observation_std = np.maximum(observations[train_indices].std(axis=(0, 1)), 1e-6)
    normalized_targets = (
        training_targets - target_mean[None, None, :]
    ) / target_std[None, None, :]
    normalized_observations = (
        observations - observation_mean[None, None, :]
    ) / observation_std[None, None, :]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    image_tensor = torch.from_numpy(images).permute(0, 1, 2, 5, 3, 4)
    observation_tensor = torch.from_numpy(normalized_observations)
    task_tensor = torch.from_numpy(task_one_hot)
    target_tensor = torch.from_numpy(targets)
    normalized_target_tensor = torch.from_numpy(normalized_targets)
    train_ids = torch.from_numpy(train_indices)
    validation_ids = torch.from_numpy(validation_indices)
    model = TemporalVisualBC(
        images.shape[2], observations.shape[2], targets.shape[2], args.action_chunk
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)

    def predict(indices: torch.Tensor) -> torch.Tensor:
        batch_images = image_tensor[indices].to(device=device, dtype=torch.float32) / 255.0
        batch_state = observation_tensor[indices].to(device)
        batch_tasks = task_tensor[indices].to(device)
        return model(batch_images, batch_state, batch_tasks)

    def infer(indices: torch.Tensor) -> torch.Tensor:
        outputs = []
        with torch.no_grad():
            for start in range(0, indices.numel(), args.eval_batch_size):
                outputs.append(predict(indices[start : start + args.eval_batch_size]).cpu())
        return torch.cat(outputs)

    model.eval()
    initial_prediction = infer(train_ids)
    initial_loss = float(
        nn.functional.mse_loss(
            initial_prediction, normalized_target_tensor[train_ids]
        ).item()
    )
    initial_balanced_loss = float(
        balanced_mse(initial_prediction, normalized_target_tensor[train_ids]).item()
    )
    started = time.perf_counter()
    history = []
    model.train()
    for step in range(args.steps):
        batch = train_ids[torch.randint(0, train_ids.numel(), (args.batch_size,))]
        prediction = predict(batch)
        loss = balanced_mse(
            prediction, normalized_target_tensor[batch].to(device)
        )
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if step == 0 or (step + 1) % 100 == 0:
            history.append({"step": step + 1, "normalized_mse": float(loss.item())})

    model.eval()
    train_normalized = infer(train_ids)
    validation_normalized = infer(validation_ids)
    train_loss = float(
        nn.functional.mse_loss(
            train_normalized, normalized_target_tensor[train_ids]
        ).item()
    )
    validation_loss = float(
        nn.functional.mse_loss(
            validation_normalized, normalized_target_tensor[validation_ids]
        ).item()
    )
    train_balanced_loss = float(
        balanced_mse(train_normalized, normalized_target_tensor[train_ids]).item()
    )
    validation_balanced_loss = float(
        balanced_mse(
            validation_normalized, normalized_target_tensor[validation_ids]
        ).item()
    )
    mean_tensor = torch.from_numpy(target_mean)
    std_tensor = torch.from_numpy(target_std)
    train_prediction = train_normalized * std_tensor + mean_tensor
    validation_prediction = validation_normalized * std_tensor + mean_tensor
    base_tensor = torch.from_numpy(target_base)
    train_prediction = train_prediction + base_tensor[train_ids]
    validation_prediction = validation_prediction + base_tensor[validation_ids]

    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "target_mean": target_mean,
            "target_std": target_std,
            "observation_mean": observation_mean,
            "observation_std": observation_std,
            "observation_fields": OBSERVATION_FIELDS,
            "action_fields": ACTION_FIELDS,
            "episodes": all_episodes,
            "training_episodes": training_episodes,
            "validation_episodes": [args.validation_episode],
            "history_offsets": history_offsets,
            "action_chunk": args.action_chunk,
            "target_mode": args.target_mode,
            "image_size": args.image_size,
            "camera_count": int(images.shape[2]),
        },
        args.checkpoint,
    )
    report = {
        "source": manifest["repo_id"],
        "baseline": "temporal four-camera visual-proprioceptive action-chunk BC",
        "episodes": all_episodes,
        "split_strategy": "leave-one-episode-out",
        "training_episodes": training_episodes,
        "validation_episodes": [args.validation_episode],
        "samples": int(images.shape[0]),
        "samples_per_episode": args.samples_per_episode,
        "training_samples": int(train_indices.size),
        "validation_samples": int(validation_indices.size),
        "camera_count": int(images.shape[2]),
        "image_size": args.image_size,
        "history_offsets_frames": list(history_offsets),
        "history_span_seconds": float(-history_offsets[0] / manifest["fps"]),
        "action_chunk": args.action_chunk,
        "action_chunk_seconds": float(args.action_chunk / manifest["fps"]),
        "target_mode": args.target_mode,
        "loss_weighting": "equal weight for ee_action, hand_cmd, and robot_q_desired",
        "target_dimension_per_step": int(targets.shape[2]),
        "proprioception_dimension": int(observations.shape[2]),
        "max_video_timestamp_error": float(sample_data["max_timestamp_error"]),
        "device": str(device),
        "steps": args.steps,
        "elapsed_seconds": time.perf_counter() - started,
        "initial_normalized_mse": initial_loss,
        "initial_balanced_normalized_mse": initial_balanced_loss,
        "final_train_normalized_mse": train_loss,
        "validation_normalized_mse": validation_loss,
        "final_train_balanced_normalized_mse": train_balanced_loss,
        "validation_balanced_normalized_mse": validation_balanced_loss,
        "loss_reduction_ratio": train_loss / initial_loss,
        "train_chunk_metrics": field_metrics(
            train_prediction, target_tensor[train_ids]
        ),
        "validation_chunk_metrics": field_metrics(
            validation_prediction, target_tensor[validation_ids]
        ),
        "validation_first_action_metrics": field_metrics(
            validation_prediction[:, 0], target_tensor[validation_ids, 0]
        ),
        "checkpoint": str(args.checkpoint),
        "scope": "Temporal official-action predictor; not connected to the 23D Isaac Sim action interface.",
        "loss_history": history,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
