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
ERROR_THRESHOLDS = {
    "robot_root_position_m": 0.05,
    "robot_root_orientation_rad": np.deg2rad(5.0),
    "robot_joint_max_abs_rad": 0.2,
    "rigid_position_m": 0.03,
    "rigid_orientation_rad": np.deg2rad(10.0),
}
STATE_REPLAY_SNAPSHOT_FRAMES = {
    0,
    160,
    180,
    187,
    202,
    220,
    300,
    403,
    465,
    599,
}


def atomic_image(frame: Any, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
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


def load_replay(
    path: Path, demo: str
) -> tuple[np.ndarray, dict[str, Any], dict[str, Any], dict[str, Any]]:
    import h5py

    with h5py.File(path, "r") as handle:
        env_args = json.loads(handle["data"].attrs["env_args"])
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
        expert_states = group["states"]
        expert = {
            "robot": {
                "root_pose": np.asarray(
                    expert_states["articulation/robot/root_pose"], dtype=np.float32
                ),
                "root_velocity": np.asarray(
                    expert_states["articulation/robot/root_velocity"],
                    dtype=np.float32,
                ),
                "joint_position": np.asarray(
                    expert_states["articulation/robot/joint_position"],
                    dtype=np.float32,
                ),
                "joint_velocity": np.asarray(
                    expert_states["articulation/robot/joint_velocity"],
                    dtype=np.float32,
                ),
            },
            "rigid_objects": {
                name: {
                    "root_pose": np.asarray(value["root_pose"], dtype=np.float32),
                    "root_velocity": np.asarray(
                        value["root_velocity"], dtype=np.float32
                    ),
                }
                for name, value in expert_states["rigid_object"].items()
            },
        }
        metadata = {
            "env_args": env_args,
            "source_success": bool(group.attrs.get("success", False)),
        }
    return actions, state, expert, metadata


def state_at(expert: dict[str, Any], frame_index: int) -> dict[str, Any]:
    robot = expert["robot"]
    return {
        "articulation": {
            "robot": {
                "root_pose": robot["root_pose"][frame_index : frame_index + 1].tolist(),
                "root_velocity": robot["root_velocity"][
                    frame_index : frame_index + 1
                ].tolist(),
                "joint_position": robot["joint_position"][
                    frame_index : frame_index + 1
                ].tolist(),
                "joint_velocity": robot["joint_velocity"][
                    frame_index : frame_index + 1
                ].tolist(),
            }
        },
        "rigid_object": {
            name: {
                "root_pose": value["root_pose"][
                    frame_index : frame_index + 1
                ].tolist(),
                "root_velocity": value["root_velocity"][
                    frame_index : frame_index + 1
                ].tolist(),
            }
            for name, value in expert["rigid_objects"].items()
        },
    }


def quaternion_error_rad(first: np.ndarray, second: np.ndarray) -> float:
    first = first / np.linalg.norm(first)
    second = second / np.linalg.norm(second)
    dot = float(np.clip(abs(np.dot(first, second)), 0.0, 1.0))
    return float(2.0 * np.arccos(dot))


def trajectory_errors(
    actual: dict[str, Any], expert: dict[str, Any], frame_index: int
) -> dict[str, float]:
    robot_actual = np.asarray(actual["robot"]["root_pose"], dtype=np.float64)[0]
    robot_expert = expert["robot"]["root_pose"][frame_index].astype(np.float64)
    joints_actual = np.asarray(
        actual["robot"]["joint_position"], dtype=np.float64
    )[0]
    joints_expert = expert["robot"]["joint_position"][frame_index].astype(
        np.float64
    )
    joint_delta = joints_actual - joints_expert
    errors = {
        "robot_root_position_m": float(
            np.linalg.norm(robot_actual[:3] - robot_expert[:3])
        ),
        "robot_root_orientation_rad": quaternion_error_rad(
            robot_actual[3:7], robot_expert[3:7]
        ),
        "robot_joint_max_abs_rad": float(np.max(np.abs(joint_delta))),
        "robot_joint_l2_rad": float(np.linalg.norm(joint_delta)),
    }
    for name, value in expert["rigid_objects"].items():
        actual_pose = np.asarray(
            actual["rigid_objects"][name]["root_pose"], dtype=np.float64
        )[0]
        expert_pose = value["root_pose"][frame_index].astype(np.float64)
        errors[f"{name}_position_m"] = float(
            np.linalg.norm(actual_pose[:3] - expert_pose[:3])
        )
        errors[f"{name}_orientation_rad"] = quaternion_error_rad(
            actual_pose[3:7], expert_pose[3:7]
        )
    return errors


def divergence_reasons(errors: dict[str, float]) -> list[str]:
    reasons: list[str] = []
    for name, value in errors.items():
        if name in ERROR_THRESHOLDS and value > ERROR_THRESHOLDS[name]:
            reasons.append(name)
        elif name.endswith("_position_m") and name != "robot_root_position_m":
            if value > ERROR_THRESHOLDS["rigid_position_m"]:
                reasons.append(name)
        elif name.endswith("_orientation_rad") and name != "robot_root_orientation_rad":
            if value > ERROR_THRESHOLDS["rigid_orientation_rad"]:
                reasons.append(name)
    return reasons


def joint_divergence_detail(
    actual: dict[str, Any], expert: dict[str, Any], frame_index: int
) -> dict[str, Any]:
    actual_values = np.asarray(
        actual["robot"]["joint_position"], dtype=np.float64
    )[0]
    expert_values = expert["robot"]["joint_position"][frame_index].astype(
        np.float64
    )
    delta = actual_values - expert_values
    index = int(np.argmax(np.abs(delta)))
    names = actual["robot"]["joint_names"]
    return {
        "index": index,
        "name": names[index],
        "actual_rad": float(actual_values[index]),
        "expert_rad": float(expert_values[index]),
        "error_rad": float(delta[index]),
    }


def save_comparison(
    output_dir: Path,
    history: dict[str, list[float]],
    first_divergence: dict[str, Any] | None,
    frames_compared: int,
) -> None:
    arrays = {name: np.asarray(values, dtype=np.float32) for name, values in history.items()}
    np.savez_compressed(output_dir.parent / "replay_errors.npz", **arrays)
    atomic_json(
        {
            "frames_compared": frames_compared,
            "thresholds": ERROR_THRESHOLDS,
            "first_divergence": first_divergence,
            "max_errors": {
                name: float(np.max(values)) if values else None
                for name, values in history.items()
            },
            "final_errors": {
                name: float(values[-1]) if values else None
                for name, values in history.items()
            },
        },
        output_dir.parent / "replay_comparison.json",
    )


def publish_frames(observation: dict[str, Any], output_dir: Path) -> None:
    for key in CAMERA_KEYS:
        if key in observation["policy"]:
            atomic_image(observation["policy"][key], output_dir / f"{key}.jpg")


def publish_state_snapshot(
    observation: dict[str, Any], output_dir: Path, frame_index: int
) -> None:
    snapshot_dir = output_dir / "state_frames"
    for key in CAMERA_KEYS:
        if key in observation["policy"]:
            atomic_image(
                observation["policy"][key],
                snapshot_dir / f"{frame_index:04d}_{key}.jpg",
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=50000, type=int)
    parser.add_argument("--authkey", default="lightwheel")
    parser.add_argument("--output-dir", required=True, type=Path)
    replay_group = parser.add_mutually_exclusive_group()
    replay_group.add_argument("--replay-hdf5", type=Path)
    replay_group.add_argument("--state-replay-hdf5", type=Path)
    parser.add_argument("--demo", default="demo_0")
    parser.add_argument("--max-frames", type=int)
    args = parser.parse_args()
    if args.max_frames is not None and args.max_frames < 1:
        parser.error("--max-frames must be positive")

    from robofinals.distributed.proxy import RemoteEnv
    from robofinals.distributed.restful import DotDict

    args.output_dir.mkdir(parents=True, exist_ok=True)
    env = RemoteEnv.make(
        address=(args.host, args.port), authkey=args.authkey.encode("utf-8")
    )
    replay_actions: np.ndarray | None = None
    initial_state: dict[str, Any] | None = None
    expert_states: dict[str, Any] | None = None
    replay_metadata: dict[str, Any] | None = None
    mode = "hold"
    replay_path = args.replay_hdf5 or args.state_replay_hdf5
    if replay_path is not None:
        replay_actions, initial_state, expert_states, replay_metadata = load_replay(
            replay_path, args.demo
        )
        mode = "state_replay" if args.state_replay_hdf5 is not None else "replay"

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
        config = make_ikea_config()
        if mode == "state_replay":
            config["execute_mode"] = "replay_state"
            config["replay_cfgs"] = {
                "hdf5_path": str(replay_path),
                "ep_meta": replay_metadata["env_args"],
                "ep_names": [args.demo],
                "add_camera_to_observation": True,
            }
        env.attach(DotDict(config))
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
        if mode == "state_replay":
            dataset_total_frames = int(expert_states["robot"]["root_pose"].shape[0])
            total_frames = dataset_total_frames
            if args.max_frames is not None:
                total_frames = min(total_frames, args.max_frames)
            verification: dict[str, dict[str, float]] = {}
            for frame_index in range(total_frames):
                observation, _ = env._svc.reset_to_state(
                    state_at(expert_states, frame_index)
                )
                publish_frames(observation, args.output_dir)
                if frame_index in STATE_REPLAY_SNAPSHOT_FRAMES:
                    publish_state_snapshot(observation, args.output_dir, frame_index)
                    actual_state = env._svc.scene_state_values()
                    verification[str(frame_index)] = trajectory_errors(
                        actual_state, expert_states, frame_index
                    )
                step = frame_index + 1
                elapsed = time.perf_counter() - started
                atomic_json(
                    {
                        "status": "running",
                        "mode": mode,
                        "demo": args.demo,
                        "frame_index": frame_index,
                        "completed_frames": step,
                        "total_frames": total_frames,
                        "dataset_total_frames": dataset_total_frames,
                        "progress_percent": 100.0 * step / total_frames,
                        "steps_per_second": step / elapsed if elapsed else 0.0,
                        "source_success": replay_metadata["source_success"],
                        "state_error": verification.get(str(frame_index)),
                        "updated_unix": time.time(),
                    },
                    args.output_dir / "status.json",
                )
            atomic_json(
                {
                    "status": "completed",
                    "mode": mode,
                    "demo": args.demo,
                    "completed_frames": total_frames,
                    "total_frames": total_frames,
                    "dataset_total_frames": dataset_total_frames,
                    "progress_percent": 100.0,
                    "steps_per_second": total_frames
                    / (time.perf_counter() - started),
                    "source_success": replay_metadata["source_success"],
                    "updated_unix": time.time(),
                },
                args.output_dir / "status.json",
            )
            atomic_json(
                {
                    "demo": args.demo,
                    "frames_checked": sorted(int(frame) for frame in verification),
                    "errors": verification,
                },
                args.output_dir.parent / "state_replay_verification.json",
            )
            return

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
            dataset_total_frames = int(replay_actions.shape[0])
            total_frames = dataset_total_frames
            if args.max_frames is not None:
                total_frames = min(total_frames, args.max_frames)
            replay_tensor = torch.tensor(
                replay_actions[:total_frames], dtype=torch.float32, device="cuda:0"
            )
            success = False
            truncated_value = False
            error_history: dict[str, list[float]] = {}
            first_divergence: dict[str, Any] | None = None
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
                actual_state = env._svc.scene_state_values()
                errors = trajectory_errors(actual_state, expert_states, frame_index)
                for name, value in errors.items():
                    error_history.setdefault(name, []).append(value)
                reasons = divergence_reasons(errors)
                if first_divergence is None and reasons:
                    first_divergence = {
                        "frame_index": frame_index,
                        "reasons": reasons,
                        "errors": errors,
                        "largest_joint_error": joint_divergence_detail(
                            actual_state, expert_states, frame_index
                        ),
                    }
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
                        "dataset_total_frames": dataset_total_frames,
                        "progress_percent": 100.0 * step / total_frames,
                        "steps_per_second": step / elapsed if elapsed else 0.0,
                        "is_success": success,
                        "is_truncated": truncated_value,
                        "trajectory_error": errors,
                        "first_divergence": first_divergence,
                        "updated_unix": time.time(),
                        "robot_root_pose_xyzw": robot_root_pose,
                        "table_root_pose_xyzw": table_root_pose,
                    },
                    args.output_dir / "status.json",
                )
                if success or truncated_value:
                    break

            save_comparison(
                args.output_dir, error_history, first_divergence, step
            )
            atomic_json(
                {
                    "status": "completed",
                    "mode": mode,
                    "demo": args.demo,
                    "completed_frames": step,
                    "total_frames": total_frames,
                    "dataset_total_frames": dataset_total_frames,
                    "progress_percent": 100.0 * step / total_frames,
                    "steps_per_second": step / (time.perf_counter() - started),
                    "is_success": success,
                    "is_truncated": truncated_value,
                    "trajectory_error": errors,
                    "first_divergence": first_divergence,
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
