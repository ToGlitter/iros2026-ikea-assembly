#!/usr/bin/env python3
"""Reset the IKEA task and run a short neutral-pose hold baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import numpy as np


CAMERA_KEYS = (
    "left_hand_camera_rgb",
    "first_person_camera_rgb",
    "right_hand_camera_rgb",
)

ACTION_LABELS = (
    "left_gripper_open_degree",
    "right_gripper_open_degree",
    "left_wrist_x",
    "left_wrist_y",
    "left_wrist_z",
    "left_wrist_qw",
    "left_wrist_qx",
    "left_wrist_qy",
    "left_wrist_qz",
    "right_wrist_x",
    "right_wrist_y",
    "right_wrist_z",
    "right_wrist_qw",
    "right_wrist_qx",
    "right_wrist_qy",
    "right_wrist_qz",
    "navigate_vel_x",
    "navigate_vel_y",
    "navigate_vel_yaw",
    "base_height",
    "torso_roll",
    "torso_pitch",
    "torso_yaw",
)

# Neutral command from frame 0 of the verified Lightwheel G1 + Dex1 demonstration.
NEUTRAL_HOLD_ACTION = (
    -1.0,
    -1.0,
    0.2000605613,
    0.16,
    0.0952299982,
    1.0,
    0.0,
    0.0,
    -5.7043508e-09,
    0.2000605613,
    -0.16,
    0.0952299982,
    1.0,
    0.0,
    0.0,
    -5.7043508e-09,
    0.0,
    0.0,
    0.0,
    0.74,
    0.0,
    0.0,
    0.0,
)


def describe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): describe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return {
            "type": type(value).__name__,
            "length": len(value),
            "items": [describe(item) for item in value[:8]],
        }

    try:
        import torch

        if torch.is_tensor(value):
            return {
                "type": "torch.Tensor",
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "device": str(value.device),
            }
    except ImportError:
        pass

    if isinstance(value, np.ndarray):
        return {
            "type": "numpy.ndarray",
            "shape": list(value.shape),
            "dtype": str(value.dtype),
        }
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return {"type": type(value).__name__, "repr": repr(value)[:300]}


def to_numpy(value: Any) -> np.ndarray:
    try:
        import torch

        if torch.is_tensor(value):
            return value.detach().cpu().numpy()
    except ImportError:
        pass
    return np.asarray(value)


def scalar_list(value: Any) -> list[Any]:
    array = to_numpy(value).reshape(-1)
    return [item.item() if hasattr(item, "item") else item for item in array]


def state_snapshot(observation: dict[str, Any]) -> dict[str, np.ndarray]:
    state = observation["embodiment_general_obs"]
    return {
        key: to_numpy(state[key]).astype(np.float64, copy=True)
        for key in ("joint_pos", "joint_vel", "eef_pos", "eef_quat", "gripper_pos")
    }


def state_delta(initial: dict[str, np.ndarray], final: dict[str, np.ndarray]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in initial:
        delta = final[key] - initial[key]
        result[key] = {
            "max_abs": float(np.max(np.abs(delta))),
            "l2": float(np.linalg.norm(delta)),
        }
    result["final_joint_velocity"] = {
        "max_abs": float(np.max(np.abs(final["joint_vel"]))),
        "l2": float(np.linalg.norm(final["joint_vel"])),
    }
    return result


def save_camera_strip(observation: dict[str, Any], output: Path) -> list[str]:
    from PIL import Image

    policy = observation.get("policy", {})
    frames: list[np.ndarray] = []
    saved_keys: list[str] = []
    for key in CAMERA_KEYS:
        if key not in policy:
            continue
        frame = to_numpy(policy[key])[0]
        frames.append(np.asarray(frame, dtype=np.uint8))
        saved_keys.append(key)

    if frames:
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.concatenate(frames, axis=1)).save(output)
    return saved_keys


def make_ikea_config() -> dict[str, Any]:
    return {
        "task": "AssembleTableTask",
        "robot": "G1-Gripper-Controller-DecoupledWBC",
        "layout": "/workspace/IROS_IKEA_V13_20260702/Scene02.usd",
        "scene_backend": "local",
        "task_backend": "local",
        "device": "cuda:0",
        "num_envs": 1,
        "rl": None,
        "robot_scale": 1.0,
        "first_person_view": True,
        "disable_fabric": False,
        "video": False,
        "for_rl": False,
        "variant": "Visual",
        "concatenate_terms": False,
        "distributed": False,
        "physics_backend": "physx",
        "seed": 42,
        "sources": None,
        "object_projects": None,
        "usd_simplify": False,
        "enable_cameras": True,
        "execute_mode": "eval",
        "replay_cfgs": {"add_camera_to_observation": True},
        "init_robot_base_pos": [-2.16, 2.4, 0.78],
        "init_robot_base_ori": [0.0, 0.0, 0.0],
        "enable_full_local_scene": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=50000, type=int)
    parser.add_argument("--authkey", default="lightwheel")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--frames-dir", required=True, type=Path)
    parser.add_argument("--steps", default=60, type=int)
    args = parser.parse_args()

    if args.steps < 0:
        parser.error("--steps must be non-negative")

    from robofinals.distributed.proxy import RemoteEnv
    from robofinals.distributed.restful import DotDict

    env = RemoteEnv.make(
        address=(args.host, args.port),
        authkey=args.authkey.encode("utf-8"),
    )
    cfg = DotDict(make_ikea_config())

    result: dict[str, Any] = {"config": dict(cfg)}
    try:
        env.attach(cfg)
        result["task_description"] = env.get_task_description()
        result["eval_metadata"] = env._svc.get_eval_metadata()
        result["action_space"] = env._svc.repr_at("action_space")
        result["action_manager"] = env._svc.repr_at("unwrapped.action_manager")
        observation, reset_info = env.reset()
        result["observation"] = describe(observation)
        result["reset_info"] = describe(reset_info)
        initial_state = state_snapshot(observation)
        result["camera_keys"] = save_camera_strip(
            observation, args.frames_dir / "step_000.png"
        )

        import torch

        action_dim = int(result["eval_metadata"]["actions_dim"])
        if action_dim != len(NEUTRAL_HOLD_ACTION):
            raise RuntimeError(
                f"expected {len(NEUTRAL_HOLD_ACTION)} actions, environment reports {action_dim}"
            )
        action = torch.tensor(
            [NEUTRAL_HOLD_ACTION], dtype=torch.float32, device="cuda:0"
        )
        terminated_history: list[list[Any]] = []
        truncated_history: list[list[Any]] = []
        extras: Any = {}
        started = time.perf_counter()
        completed_steps = 0
        for step in range(args.steps):
            observation, _, terminated, truncated, extras = env.step(action)
            completed_steps = step + 1
            terminated_values = scalar_list(terminated)
            truncated_values = scalar_list(truncated)
            if any(bool(value) for value in terminated_values):
                terminated_history.append(terminated_values)
            if any(bool(value) for value in truncated_values):
                truncated_history.append(truncated_values)
            if any(bool(value) for value in terminated_values + truncated_values):
                break

        elapsed = time.perf_counter() - started
        final_state = state_snapshot(observation)
        save_camera_strip(observation, args.frames_dir / f"step_{completed_steps:03d}.png")
        result["rollout"] = {
            "requested_steps": args.steps,
            "completed_steps": completed_steps,
            "action_shape": list(action.shape),
            "action_labels": list(ACTION_LABELS),
            "hold_action": list(NEUTRAL_HOLD_ACTION),
            "elapsed_seconds": elapsed,
            "steps_per_second": completed_steps / elapsed if elapsed else None,
            "terminated_events": terminated_history,
            "truncated_events": truncated_history,
            "final_extras": describe(extras),
            "state_delta": state_delta(initial_state, final_state),
            "frames": [
                str(args.frames_dir / "step_000.png"),
                str(args.frames_dir / f"step_{completed_steps:03d}.png"),
            ],
        }
        result["status"] = "hold_ok"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = repr(exc)
        raise
    finally:
        try:
            env.close()
        except Exception as exc:
            result["close_warning"] = repr(exc)
        try:
            env.close_connection()
        except Exception as exc:
            result["connection_close_warning"] = repr(exc)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
