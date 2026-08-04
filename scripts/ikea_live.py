#!/usr/bin/env python3
"""Publish a neutral hold or HDF5 expert replay to the live camera viewer."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from typing import Any

import numpy as np
from PIL import Image
import torch

from ikea_smoke import CAMERA_KEYS, NEUTRAL_HOLD_ACTION, make_ikea_config, to_numpy


ROBOT_BASE_POSE_XYZW = (-2.41, 2.4, 0.78, 0.0, 0.0, 0.0, 1.0)


def atomic_image(frame: Any, output: Path) -> None:
    array = np.asarray(to_numpy(frame)[0], dtype=np.uint8)
    temporary = output.with_suffix(".tmp.jpg")
    Image.fromarray(array).save(temporary, quality=88)
    os.replace(temporary, output)


def atomic_json(value: dict[str, Any], output: Path) -> None:
    temporary = output.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, output)


def remote_pose(env: Any, path: str) -> list[float]:
    # The server helper unwraps Warp ProxyArray -> CUDA tensor -> CPU list.
    value = env._svc.pose_values(path)
    return [float(item) for item in np.asarray(value)[0].reshape(-1)]


def load_replay(path: Path, demo: str) -> tuple[np.ndarray, dict[str, Any]]:
    import h5py

    with h5py.File(path, "r") as handle:
        group = handle[f"data/{demo}"]
        actions = np.asarray(group["actions"], dtype=np.float32)
        initial = group["initial_state"]
        robot = initial["articulation/robot"]
        rigid_objects = {
            name: {
                "root_pose": np.asarray(value["root_pose"])[0].tolist(),
                "root_velocity": np.asarray(value["root_velocity"])[0].tolist(),
            }
            for name, value in initial["rigid_object"].items()
        }
        state = {
            "robot": {
                "root_pose": np.asarray(robot["root_pose"])[0].tolist(),
                "root_velocity": np.asarray(robot["root_velocity"])[0].tolist(),
                "joint_position": np.asarray(robot["joint_position"])[0].tolist(),
                "joint_velocity": np.asarray(robot["joint_velocity"])[0].tolist(),
            },
            "rigid_objects": rigid_objects,
        }
    return actions, state


def publish_frames(observation: dict[str, Any], output_dir: Path) -> None:
    for key in CAMERA_KEYS:
        if key in observation["policy"]:
            atomic_image(observation["policy"][key], output_dir / f"{key}.jpg")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=50000, type=int)
    parser.add_argument("--authkey", default="lightwheel")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--replay-hdf5", type=Path)
    parser.add_argument("--demo", default="demo_0")
    args = parser.parse_args()

    from robofinals.distributed.proxy import RemoteEnv
    from robofinals.distributed.restful import DotDict

    args.output_dir.mkdir(parents=True, exist_ok=True)
    env = RemoteEnv.make(
        address=(args.host, args.port), authkey=args.authkey.encode("utf-8")
    )
    replay_actions: np.ndarray | None = None
    initial_state: dict[str, Any] | None = None
    mode = "hold"
    if args.replay_hdf5 is not None:
        replay_actions, initial_state = load_replay(args.replay_hdf5, args.demo)
        mode = "replay"

    hold_action = torch.tensor(
        [NEUTRAL_HOLD_ACTION], dtype=torch.float32, device="cuda:0"
    )
    step = 0
    resets = 0
    started = time.perf_counter()
    try:
        atomic_json(
            {
                "status": "initializing",
                "phase": "attaching",
                "mode": mode,
                "updated_unix": time.time(),
            },
            args.output_dir / "status.json",
        )
        env.attach(DotDict(make_ikea_config()))
        atomic_json(
            {
                "status": "initializing",
                "phase": "resetting",
                "mode": mode,
                "updated_unix": time.time(),
            },
            args.output_dir / "status.json",
        )
        observation, _ = env.reset()
        if initial_state is None:
            env._svc.set_robot_pose(ROBOT_BASE_POSE_XYZW)
        else:
            env._svc.set_initial_state(initial_state)
        robot_root_pose = remote_pose(
            env, "scene.articulations.robot.data.root_pose_w"
        )
        table_root_pose = remote_pose(
            env, "scene.rigid_objects.Table278_Table278.data.root_pose_w"
        )

        if replay_actions is not None:
            total_frames = int(replay_actions.shape[0])
            replay_tensor = torch.tensor(
                replay_actions, dtype=torch.float32, device="cuda:0"
            )
            success = False
            truncated_value = False
            for frame_index in range(total_frames):
                observation, _, terminated, truncated, _ = env.step(
                    replay_tensor[frame_index].unsqueeze(0)
                )
                step = frame_index + 1
                success = bool(to_numpy(terminated).any())
                truncated_value = bool(to_numpy(truncated).any())
                if step % 30 == 0 or step == 1:
                    robot_root_pose = remote_pose(
                        env, "scene.articulations.robot.data.root_pose_w"
                    )
                publish_frames(observation, args.output_dir)
                elapsed = time.perf_counter() - started
                atomic_json(
                    {
                        "status": "running",
                        "mode": mode,
                        "demo": args.demo,
                        "frame_index": frame_index,
                        "completed_frames": step,
                        "total_frames": total_frames,
                        "progress_percent": 100.0 * step / total_frames,
                        "steps_per_second": step / elapsed if elapsed else 0.0,
                        "is_success": success,
                        "is_truncated": truncated_value,
                        "updated_unix": time.time(),
                        "robot_root_pose_xyzw": robot_root_pose,
                        "table_root_pose_xyzw": table_root_pose,
                    },
                    args.output_dir / "status.json",
                )
                if success or truncated_value:
                    break

            atomic_json(
                {
                    "status": "completed",
                    "mode": mode,
                    "demo": args.demo,
                    "completed_frames": step,
                    "total_frames": total_frames,
                    "progress_percent": 100.0 * step / total_frames,
                    "steps_per_second": step / (time.perf_counter() - started),
                    "is_success": success,
                    "is_truncated": truncated_value,
                    "updated_unix": time.time(),
                    "robot_root_pose_xyzw": robot_root_pose,
                    "table_root_pose_xyzw": table_root_pose,
                },
                args.output_dir / "status.json",
            )
            return

        while True:
            publish_frames(observation, args.output_dir)

            elapsed = time.perf_counter() - started
            atomic_json(
                {
                    "status": "running",
                    "mode": mode,
                    "step": step,
                    "resets": resets,
                    "steps_per_second": step / elapsed if elapsed else 0.0,
                    "updated_unix": time.time(),
                    "robot_root_pose_xyzw": robot_root_pose,
                    "table_root_pose_xyzw": table_root_pose,
                },
                args.output_dir / "status.json",
            )
            observation, _, terminated, truncated, _ = env.step(hold_action)
            step += 1
            if step % 30 == 0:
                robot_root_pose = remote_pose(
                    env, "scene.articulations.robot.data.root_pose_w"
                )
            if bool(to_numpy(terminated).any() or to_numpy(truncated).any()):
                observation, _ = env.reset()
                env._svc.set_robot_pose(ROBOT_BASE_POSE_XYZW)
                robot_root_pose = remote_pose(
                    env, "scene.articulations.robot.data.root_pose_w"
                )
                resets += 1
    except Exception as error:
        atomic_json(
            {
                "status": "error",
                "mode": mode,
                "message": f"{type(error).__name__}: {error}",
                "updated_unix": time.time(),
            },
            args.output_dir / "status.json",
        )
        raise
    finally:
        try:
            env.close()
        except Exception:
            pass
        try:
            env.close_connection()
        except Exception:
            pass


if __name__ == "__main__":
    main()
