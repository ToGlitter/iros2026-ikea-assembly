#!/usr/bin/env python3
"""Train a compact four-camera BC model on five official episodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import av
import numpy as np
from PIL import Image
import pyarrow.parquet as pq
import torch
from torch import nn


ACTION_FIELDS = (
    "action.ee_action",
    "action.hand_cmd",
    "action.robot_q_desired",
)
OBSERVATION_FIELDS = (
    "observation.state.ee_state",
    "observation.state.hand_state",
    "observation.state.robot_q_current",
)
TASK_COUNT = 8


def decode_frames(
    path: Path, timestamps: np.ndarray, fps: float, image_size: int
) -> tuple[np.ndarray, float]:
    images = []
    errors = []
    target_index = 0
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        seek_time = max(0.0, float(timestamps[0]) - 2.0)
        container.seek(
            int(seek_time / float(stream.time_base)),
            stream=stream,
            any_frame=False,
            backward=True,
        )
        for frame in container.decode(stream):
            frame_time = float(frame.time)
            if frame_time < float(timestamps[target_index]) - 0.5 / fps:
                continue
            image = frame.to_image().resize((image_size, image_size), Image.Resampling.BILINEAR)
            images.append(np.asarray(image, dtype=np.uint8))
            errors.append(frame_time - float(timestamps[target_index]))
            target_index += 1
            if target_index == len(timestamps):
                break
    if target_index != len(timestamps):
        raise RuntimeError(f"decoded {target_index}/{len(timestamps)} targets from {path}")
    return np.stack(images), float(np.max(np.abs(errors)))


def table_vectors(table: object, fields: tuple[str, ...]) -> np.ndarray:
    return np.concatenate(
        [
            np.asarray(table[field].combine_chunks().to_pylist(), dtype=np.float32)
            for field in fields
        ],
        axis=1,
    )


def build_cache(
    dataset_root: Path,
    manifest: dict,
    samples_per_episode: int,
    image_size: int,
) -> dict[str, np.ndarray]:
    table_cache = {}
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
                    "episode_index", "frame_index", "timestamp", "task_index",
                    *OBSERVATION_FIELDS, *ACTION_FIELDS,
                ],
            )
        table = table_cache[data_path]
        all_episode_ids = np.asarray(table["episode_index"].combine_chunks().to_numpy())
        row_indices = np.flatnonzero(all_episode_ids == episode["episode_index"])
        sample_count = min(samples_per_episode, row_indices.size)
        within_episode = np.linspace(0, row_indices.size - 1, sample_count, dtype=np.int64)
        selected = table.take(row_indices[within_episode])
        sample_timestamps = np.asarray(
            selected["timestamp"].combine_chunks().to_numpy(), dtype=np.float64
        )
        camera_images = []
        for camera, metadata in sorted(episode["videos"].items()):
            targets = sample_timestamps + float(metadata["from_timestamp"])
            decoded, timestamp_error = decode_frames(
                dataset_root / metadata["path"], targets, fps, image_size
            )
            camera_images.append(decoded)
            max_timestamp_error = max(max_timestamp_error, timestamp_error)
        images.append(np.stack(camera_images, axis=1))
        observations.append(table_vectors(selected, OBSERVATION_FIELDS))
        actions.append(table_vectors(selected, ACTION_FIELDS))
        tasks.append(
            np.asarray(selected["task_index"].combine_chunks().to_numpy(), dtype=np.int64)
        )
        episode_ids.append(np.full(sample_count, episode["episode_index"], dtype=np.int64))
        frame_ids.append(
            np.asarray(selected["frame_index"].combine_chunks().to_numpy(), dtype=np.int64)
        )
    return {
        "images": np.concatenate(images),
        "observations": np.concatenate(observations),
        "actions": np.concatenate(actions),
        "tasks": np.concatenate(tasks),
        "episode_ids": np.concatenate(episode_ids),
        "frame_ids": np.concatenate(frame_ids),
        "max_timestamp_error": np.asarray(max_timestamp_error),
    }


class VisualBC(nn.Module):
    def __init__(
        self, camera_count: int, state_dimension: int, action_dimension: int
    ) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(3, 16, kernel_size=5, stride=2, padding=2),
            nn.GELU(),
            nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1),
            nn.GELU(),
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
            nn.GELU(),
            nn.AdaptiveAvgPool2d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(camera_count * 64 + state_dimension + TASK_COUNT, 256),
            nn.GELU(),
            nn.Linear(256, 256),
            nn.GELU(),
            nn.Linear(256, action_dimension),
        )

    def forward(
        self, images: torch.Tensor, state: torch.Tensor, tasks: torch.Tensor
    ) -> torch.Tensor:
        batch, cameras, channels, height, width = images.shape
        encoded = self.encoder(images.reshape(batch * cameras, channels, height, width))
        encoded = encoded.reshape(batch, cameras * 64)
        return self.head(torch.cat([encoded, state, tasks], dim=1))


def metrics(prediction: torch.Tensor, target: torch.Tensor) -> dict[str, dict[str, float]]:
    result = {}
    offset = 0
    for field, size in zip(ACTION_FIELDS, (12, 2, 36)):
        delta = prediction[:, offset : offset + size] - target[:, offset : offset + size]
        result[field] = {
            "mae": float(delta.abs().mean().item()),
            "rmse": float(delta.square().mean().sqrt().item()),
        }
        offset += size
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples-per-episode", type=int, default=256)
    parser.add_argument("--image-size", type=int, default=64)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--validation-episode",
        type=int,
        help="Reserve one complete episode for validation.",
    )
    args = parser.parse_args()

    torch.manual_seed(0)
    np.random.seed(0)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.cache.exists():
        cached = np.load(args.cache)
        sample_data = {key: cached[key] for key in cached.files}
    if not args.cache.exists() or "observations" not in sample_data:
        sample_data = build_cache(
            args.dataset_root, manifest, args.samples_per_episode, args.image_size
        )
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(args.cache, **sample_data)

    images = sample_data["images"]
    observation = sample_data["observations"].astype(np.float32)
    target = sample_data["actions"].astype(np.float32)
    task_one_hot = np.eye(TASK_COUNT, dtype=np.float32)[sample_data["tasks"]]
    episode_ids = sample_data["episode_ids"]
    all_episodes = sorted(set(episode_ids.tolist()))
    if args.validation_episode is not None:
        if args.validation_episode not in all_episodes:
            raise ValueError(
                f"validation episode {args.validation_episode} is not in {all_episodes}"
            )
        train_indices = np.flatnonzero(episode_ids != args.validation_episode)
        validation_indices = np.flatnonzero(episode_ids == args.validation_episode)
        split_strategy = "leave-one-episode-out"
        training_episodes = [
            episode for episode in all_episodes if episode != args.validation_episode
        ]
        validation_episodes = [args.validation_episode]
    else:
        train_parts = []
        validation_parts = []
        for episode_index in all_episodes:
            indices = np.flatnonzero(episode_ids == episode_index)
            np.random.shuffle(indices)
            split = max(1, len(indices) // 10)
            validation_parts.append(indices[:split])
            train_parts.append(indices[split:])
        train_indices = np.concatenate(train_parts)
        validation_indices = np.concatenate(validation_parts)
        split_strategy = "within-episode-random-10-percent"
        training_episodes = all_episodes
        validation_episodes = all_episodes
    target_mean = target[train_indices].mean(axis=0)
    target_std = np.maximum(target[train_indices].std(axis=0), 1e-6)
    observation_mean = observation[train_indices].mean(axis=0)
    observation_std = np.maximum(observation[train_indices].std(axis=0), 1e-6)
    normalized_target = (target - target_mean) / target_std
    normalized_observation = (observation - observation_mean) / observation_std

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    image_tensor = torch.from_numpy(images).permute(0, 1, 4, 2, 3)
    observation_tensor = torch.from_numpy(normalized_observation)
    task_tensor = torch.from_numpy(task_one_hot)
    target_tensor = torch.from_numpy(target)
    normalized_tensor = torch.from_numpy(normalized_target)
    train_ids = torch.from_numpy(train_indices)
    validation_ids = torch.from_numpy(validation_indices)
    model = VisualBC(images.shape[1], observation.shape[1], target.shape[1]).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)

    def predict(indices: torch.Tensor) -> torch.Tensor:
        batch_images = image_tensor[indices].to(device=device, dtype=torch.float32) / 255.0
        batch_state = observation_tensor[indices].to(device)
        batch_tasks = task_tensor[indices].to(device)
        return model(batch_images, batch_state, batch_tasks)

    with torch.no_grad():
        initial_loss = float(
            nn.functional.mse_loss(predict(train_ids), normalized_tensor[train_ids].to(device)).item()
        )
    started = time.perf_counter()
    history = []
    model.train()
    for step in range(args.steps):
        batch = train_ids[torch.randint(0, train_ids.numel(), (args.batch_size,))]
        prediction = predict(batch)
        loss = nn.functional.mse_loss(prediction, normalized_tensor[batch].to(device))
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if step == 0 or (step + 1) % 100 == 0:
            history.append({"step": step + 1, "normalized_mse": float(loss.item())})

    model.eval()
    mean_tensor = torch.from_numpy(target_mean).to(device)
    std_tensor = torch.from_numpy(target_std).to(device)
    with torch.no_grad():
        train_normalized = predict(train_ids)
        validation_normalized = predict(validation_ids)
        train_loss = float(
            nn.functional.mse_loss(train_normalized, normalized_tensor[train_ids].to(device)).item()
        )
        validation_loss = float(
            nn.functional.mse_loss(
                validation_normalized, normalized_tensor[validation_ids].to(device)
            ).item()
        )
        train_prediction = train_normalized * std_tensor + mean_tensor
        validation_prediction = validation_normalized * std_tensor + mean_tensor

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
            "validation_episodes": validation_episodes,
            "image_size": args.image_size,
            "camera_count": int(images.shape[1]),
        },
        args.checkpoint,
    )
    report = {
        "source": manifest["repo_id"],
        "baseline": "four-camera visual-proprioceptive BC pipeline smoke test",
        "episodes": all_episodes,
        "split_strategy": split_strategy,
        "training_episodes": training_episodes,
        "validation_episodes": validation_episodes,
        "samples": int(images.shape[0]),
        "samples_per_episode": args.samples_per_episode,
        "training_samples": int(train_indices.size),
        "validation_samples": int(validation_indices.size),
        "camera_count": int(images.shape[1]),
        "image_size": args.image_size,
        "target_dimension": int(target.shape[1]),
        "proprioception_dimension": int(observation.shape[1]),
        "max_video_timestamp_error": float(sample_data["max_timestamp_error"]),
        "device": str(device),
        "steps": args.steps,
        "elapsed_seconds": time.perf_counter() - started,
        "initial_normalized_mse": initial_loss,
        "final_train_normalized_mse": train_loss,
        "validation_normalized_mse": validation_loss,
        "loss_reduction_ratio": train_loss / initial_loss,
        "train_metrics": metrics(train_prediction, target_tensor[train_ids].to(device)),
        "validation_metrics": metrics(
            validation_prediction, target_tensor[validation_ids].to(device)
        ),
        "checkpoint": str(args.checkpoint),
        "scope": "Five-episode visual-proprioceptive training pipeline; not yet connected to the 23D Isaac Sim action interface.",
        "loss_history": history,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
