#!/usr/bin/env python3
"""Train a short-history Lightwheel proprioception -> 23D action head."""

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
GROUPS = {"grippers": (0, 2), "wrists": (2, 16), "navigation": (16, 19), "base_height": (19, 20), "torso_rpy": (20, 23)}


def read_split(root: Path, files: list[dict], samples_per_demo: int, history: int):
    states, actions, demos = [], [], []
    for item in files:
        path = root / item["path"]
        with h5py.File(path, "r") as hdf5:
            for name in sorted(n for n in hdf5["data"] if n.startswith("demo_")):
                demo = hdf5[f"data/{name}"]
                if not bool(demo.attrs.get("success", False)):
                    continue
                fields = [np.asarray(demo[field], dtype=np.float32) for field in STATE_FIELDS]
                full_state = np.concatenate(fields, axis=1)
                full_action = np.asarray(demo["actions"], dtype=np.float32)
                count = min(samples_per_demo, len(full_action))
                indices = np.linspace(0, len(full_action) - 1, count, dtype=np.int64)
                windows = []
                for index in indices:
                    start = max(0, int(index) - history + 1)
                    window = full_state[start : int(index) + 1]
                    if len(window) < history:
                        window = np.concatenate([np.repeat(window[:1], history - len(window), axis=0), window], axis=0)
                    windows.append(window.reshape(-1))
                states.append(np.asarray(windows, dtype=np.float32))
                actions.append(full_action[indices])
                demos.append({"path": str(path), "demo": name, "frame_count": len(full_action), "sample_count": count, "history": history})
    if not states:
        raise RuntimeError("no successful demos found")
    return np.concatenate(states), np.concatenate(actions), demos


class ActionHead(nn.Module):
    def __init__(self, dimension: int):
        super().__init__()
        self.model = nn.Sequential(nn.Linear(dimension, 512), nn.GELU(), nn.Linear(512, 256), nn.GELU(), nn.Linear(256, 23))

    def forward(self, x):
        return self.model(x)


def metrics(prediction, target):
    result = {}
    for name, (start, end) in GROUPS.items():
        delta = prediction[:, start:end] - target[:, start:end]
        result[name] = {"mae": float(delta.abs().mean()), "rmse": float(delta.square().mean().sqrt())}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history", type=int, default=4)
    parser.add_argument("--samples-per-demo", type=int, default=512)
    parser.add_argument("--steps", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=256)
    args = parser.parse_args()
    if args.history < 1:
        parser.error("--history must be positive")
    torch.manual_seed(0)
    np.random.seed(0)
    selection = json.loads(args.selection.read_text(encoding="utf-8"))["lightwheel"]["splits"]
    train_x, train_a, train_d = read_split(args.dataset_root, selection["train"], args.samples_per_demo, args.history)
    val_x, val_a, val_d = read_split(args.dataset_root, selection["validation"], args.samples_per_demo, args.history)
    test_x, test_a, test_d = read_split(args.dataset_root, selection["test"], args.samples_per_demo, args.history)
    state_mean, state_std = train_x.mean(0), np.maximum(train_x.std(0), 1e-6)
    action_mean, action_std = train_a.mean(0), np.maximum(train_a.std(0), 1e-6)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    norm = lambda x: torch.from_numpy(((x - state_mean) / state_std).astype(np.float32)).to(device)
    train_x, val_x, test_x = norm(train_x), norm(val_x), norm(test_x)
    train_y = torch.from_numpy(((train_a - action_mean) / action_std).astype(np.float32)).to(device)
    val_y = torch.from_numpy(((val_a - action_mean) / action_std).astype(np.float32)).to(device)
    test_y = torch.from_numpy(((test_a - action_mean) / action_std).astype(np.float32)).to(device)
    model = ActionHead(train_x.shape[1]).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    started = time.perf_counter()
    history_log = []
    for step in range(args.steps):
        batch = torch.randint(0, train_x.shape[0], (args.batch_size,), device=device)
        loss = nn.functional.mse_loss(model(train_x[batch]), train_y[batch])
        optimizer.zero_grad(set_to_none=True); loss.backward(); optimizer.step()
        if step == 0 or (step + 1) % 100 == 0:
            history_log.append({"step": step + 1, "normalized_mse": float(loss)})
    model.eval()
    with torch.no_grad():
        pred_train = model(train_x) * torch.from_numpy(action_std).to(device) + torch.from_numpy(action_mean).to(device)
        pred_val = model(val_x) * torch.from_numpy(action_std).to(device) + torch.from_numpy(action_mean).to(device)
        pred_test = model(test_x) * torch.from_numpy(action_std).to(device) + torch.from_numpy(action_mean).to(device)
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state_dict": model.state_dict(), "state_mean": state_mean, "state_std": state_std, "action_mean": action_mean, "action_std": action_std, "state_fields": STATE_FIELDS, "history": args.history, "action_groups": GROUPS}, args.checkpoint)
    report = {"baseline": "four-frame temporal 316D proprioception to 23D Isaac Sim action head", "history": args.history, "device": str(device), "steps": args.steps, "train_samples": int(train_x.shape[0]), "validation_samples": int(val_x.shape[0]), "test_samples": int(test_x.shape[0]), "train_metrics": metrics(pred_train, torch.from_numpy(train_a).to(device)), "validation_metrics": metrics(pred_val, torch.from_numpy(val_a).to(device)), "test_metrics": metrics(pred_test, torch.from_numpy(test_a).to(device)), "checkpoint": str(args.checkpoint), "elapsed_seconds": time.perf_counter() - started, "train_demos": train_d, "validation_demos": val_d, "test_demos": test_d, "loss_history": history_log, "scope": "supervised temporal action prediction; rollout validation pending"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
