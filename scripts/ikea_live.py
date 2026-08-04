#!/usr/bin/env python3
"""Continuously step the IKEA environment and publish camera frames to disk."""

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=50000, type=int)
    parser.add_argument("--authkey", default="lightwheel")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    from robofinals.distributed.proxy import RemoteEnv
    from robofinals.distributed.restful import DotDict

    args.output_dir.mkdir(parents=True, exist_ok=True)
    env = RemoteEnv.make(
        address=(args.host, args.port), authkey=args.authkey.encode("utf-8")
    )
    action = torch.tensor(
        [NEUTRAL_HOLD_ACTION], dtype=torch.float32, device="cuda:0"
    )
    step = 0
    resets = 0
    started = time.perf_counter()
    try:
        atomic_json(
            {"status": "initializing", "phase": "attaching", "updated_unix": time.time()},
            args.output_dir / "status.json",
        )
        env.attach(DotDict(make_ikea_config()))
        atomic_json(
            {"status": "initializing", "phase": "resetting", "updated_unix": time.time()},
            args.output_dir / "status.json",
        )
        observation, _ = env.reset()
        env._svc.set_robot_pose(ROBOT_BASE_POSE_XYZW)
        robot_root_pose = remote_pose(
            env, "scene.articulations.robot.data.root_pose_w"
        )
        table_root_pose = remote_pose(
            env, "scene.rigid_objects.Table278_Table278.data.root_pose_w"
        )
        while True:
            for key in CAMERA_KEYS:
                if key in observation["policy"]:
                    atomic_image(
                        observation["policy"][key],
                        args.output_dir / f"{key}.jpg",
                    )

            elapsed = time.perf_counter() - started
            atomic_json(
                {
                    "status": "running",
                    "step": step,
                    "resets": resets,
                    "steps_per_second": step / elapsed if elapsed else 0.0,
                    "updated_unix": time.time(),
                    "robot_root_pose_xyzw": robot_root_pose,
                    "table_root_pose_xyzw": table_root_pose,
                },
                args.output_dir / "status.json",
            )
            observation, _, terminated, truncated, _ = env.step(action)
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
