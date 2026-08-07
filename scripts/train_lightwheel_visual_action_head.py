#!/usr/bin/env python3
"""Train a compact Lightwheel three-camera visual-proprioceptive 23D head."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import h5py
import numpy as np
from PIL import Image
import torch
from torch import nn


CAMERAS = ("first_person_camera_rgb", "left_hand_camera_rgb", "right_hand_camera_rgb")
STATE_FIELDS = (
    "states/articulation/robot/root_pose",
    "states/articulation/robot/root_velocity",
    "states/articulation/robot/joint_position",
    "states/articulation/robot/joint_velocity",
)
ACTION_GROUPS = {
    "grippers": (0, 2),
    "wrists": (2, 16),
    "navigation": (16, 19),
    "base_height": (19, 20),
    "torso_rpy": (20, 23),
}


def read_split(dataset_root: Path, files: list[dict], samples_per_demo: int, image_size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    images: list[np.ndarray] = []
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    demos: list[dict] = []
    for item in files:
        path = dataset_root / item["path"]
        with h5py.File(path, "r") as hdf5:
            for demo_name in sorted(name for name in hdf5["data"] if name.startswith("demo_")):
                demo = hdf5[f"data/{demo_name}"]
                if not bool(demo.attrs.get("success", False)):
                    continue
                frame_count = int(demo["actions"].shape[0])
                count = min(samples_per_demo, frame_count)
                indices = np.linspace(0, frame_count - 1, count, dtype=np.int64)
                camera_values = []
                for camera in CAMERAS:
                    source = demo[f"obs/{camera}"][indices]
                    camera_values.append(
                        np.stack(
                            [np.asarray(Image.fromarray(frame).resize((image_size, image_size), Image.Resampling.BILINEAR), dtype=np.uint8) for frame in source]
                        )
                    )
                images.append(np.stack(camera_values, axis=1))
                states.append(np.concatenate([np.asarray(demo[field][indices], dtype=np.float32) for field in STATE_FIELDS], axis=1))
                actions.append(np.asarray(demo["actions"][indices], dtype=np.float32))
                demos.append({"path": str(path), "demo": demo_name, "frame_count": frame_count, "sample_count": count})
    if not images:
        raise RuntimeError("no successful demos found for split")
    return np.concatenate(images), np.concatenate(states), np.concatenate(actions), demos


class VisualActionHead(nn.Module):
    def __init__(self, camera_count: int, state_dimension: int) -> None:
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
            nn.Linear(camera_count * 64 + state_dimension, 256),
            nn.GELU(),
            nn.Linear(256, 256),
            nn.GELU(),
            nn.Linear(256, 23),
        )

    def forward(self, images: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        batch, cameras, channels, height, width = images.shape
        encoded = self.encoder(images.reshape(batch * cameras, channels, height, width))
        encoded = encoded.reshape(batch, cameras * 64)
        return self.head(torch.cat([encoded, state], dim=1))


def metrics(prediction: torch.Tensor, target: torch.Tensor) -> dict[str, dict[str, float]]:
    result = {}
    for name, (start, end) in ACTION_GROUPS.items():
        delta = prediction[:, start:end] - target[:, start:end]
        result[name] = {"mae": float(delta.abs().mean().item()), "rmse": float(delta.square().mean().sqrt().item())}
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples-per-demo", type=int, default=256)
    parser.add_argument("--image-size", type=int, default=64)
    parser.add_argument("--steps", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    torch.manual_seed(0)
    np.random.seed(0)
    selection = json.loads(args.selection.read_text(encoding="utf-8"))["lightwheel"]["splits"]
    train_images, train_state, train_action, train_demos = read_split(args.dataset_root, selection["train"], args.samples_per_demo, args.image_size)
    validation_images, validation_state, validation_action, validation_demos = read_split(args.dataset_root, selection["validation"], args.samples_per_demo, args.image_size)
    test_images, test_state, test_action, test_demos = read_split(args.dataset_root, selection["test"], args.samples_per_demo, args.image_size)

    state_mean = train_state.mean(axis=0)
    state_std = np.maximum(train_state.std(axis=0), 1e-6)
    action_mean = train_action.mean(axis=0)
    action_std = np.maximum(train_action.std(axis=0), 1e-6)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    image_tensor = lambda value: torch.from_numpy(value).permute(0, 1, 4, 2, 3).to(device=device, dtype=torch.float32) / 255.0
    train_x_image = image_tensor(train_images)
    validation_x_image = image_tensor(validation_images)
    test_x_image = image_tensor(test_images)
    train_x_state = torch.from_numpy((train_state - state_mean) / state_std).to(device)
    validation_x_state = torch.from_numpy((validation_state - state_mean) / state_std).to(device)
    test_x_state = torch.from_numpy((test_state - state_mean) / state_std).to(device)
    train_y = torch.from_numpy((train_action - action_mean) / action_std).to(device)
    validation_y = torch.from_numpy((validation_action - action_mean) / action_std).to(device)
    test_y = torch.from_numpy((test_action - action_mean) / action_std).to(device)
    model = VisualActionHead(3, train_state.shape[1]).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    with torch.no_grad():
        initial_loss = float(nn.functional.mse_loss(model(train_x_image, train_x_state), train_y).item())
    history = []
    started = time.perf_counter()
    model.train()
    for step in range(args.steps):
        batch = torch.randint(0, train_x_state.shape[0], (args.batch_size,), device=device)
        prediction = model(train_x_image[batch], train_x_state[batch])
        loss = nn.functional.mse_loss(prediction, train_y[batch])
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if step == 0 or (step + 1) % 100 == 0:
            history.append({"step": step + 1, "normalized_mse": float(loss.item())})

    model.eval()
    action_mean_tensor = torch.from_numpy(action_mean).to(device)
    action_std_tensor = torch.from_numpy(action_std).to(device)
    with torch.no_grad():
        train_normalized = model(train_x_image, train_x_state)
        validation_normalized = model(validation_x_image, validation_x_state)
        test_normalized = model(test_x_image, test_x_state)
        train_prediction = train_normalized * action_std_tensor + action_mean_tensor
        validation_prediction = validation_normalized * action_std_tensor + action_mean_tensor
        test_prediction = test_normalized * action_std_tensor + action_mean_tensor
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state_dict": model.state_dict(), "state_mean": state_mean, "state_std": state_std, "action_mean": action_mean, "action_std": action_std, "state_fields": STATE_FIELDS, "action_groups": ACTION_GROUPS, "camera_names": CAMERAS, "image_size": args.image_size}, args.checkpoint)
    report = {
        "source": "LightwheelAI/iros2026-ikea-assembly",
        "baseline": "three-camera visual-proprioceptive 79D to 23D Isaac Sim action head",
        "split_file_counts": {name: len(selection[name]) for name in ("train", "validation", "test")},
        "split_sample_counts": {"train": int(train_state.shape[0]), "validation": int(validation_state.shape[0]), "test": int(test_state.shape[0])},
        "state_dimension": int(train_state.shape[1]), "action_dimension": 23, "camera_count": 3, "image_size": args.image_size,
        "device": str(device), "steps": args.steps, "elapsed_seconds": time.perf_counter() - started,
        "initial_train_normalized_mse": initial_loss,
        "final_train_normalized_mse": float(nn.functional.mse_loss(train_normalized, train_y).item()),
        "validation_normalized_mse": float(nn.functional.mse_loss(validation_normalized, validation_y).item()),
        "test_normalized_mse": float(nn.functional.mse_loss(test_normalized, test_y).item()),
        "train_metrics": metrics(train_prediction, torch.from_numpy(train_action).to(device)),
        "validation_metrics": metrics(validation_prediction, torch.from_numpy(validation_action).to(device)),
        "test_metrics": metrics(test_prediction, torch.from_numpy(test_action).to(device)),
        "train_demos": train_demos, "validation_demos": validation_demos, "test_demos": test_demos,
        "checkpoint": str(args.checkpoint), "scope": "Supervised RGB/proprioception action prediction only; not yet a closed-loop Isaac Sim rollout.", "loss_history": history,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
