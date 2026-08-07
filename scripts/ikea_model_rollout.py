#!/usr/bin/env python3
"""Closed-loop Lightwheel state-head rollout in the Isaac Sim IKEA task.

The checkpoint is the first-stage 79D proprioception -> 23D action head.  This
script deliberately starts with a short held-out rollout and records both the
pre-action state and the post-WBC state so that action/coordinate mismatches are
visible before attempting contact-rich manipulation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import torch

from ikea_live import (
    atomic_json,
    divergence_reasons,
    joint_divergence_detail,
    load_replay,
    make_ikea_config,
    publish_frames,
    state_at,
    to_numpy,
    trajectory_errors,
)


class ActionHead(torch.nn.Module):
    def __init__(self, state_dimension: int, hidden1: int = 256, hidden2: int = 256) -> None:
        super().__init__()
        self.model = torch.nn.Sequential(
            torch.nn.Linear(state_dimension, hidden1),
            torch.nn.GELU(),
            torch.nn.Linear(hidden1, hidden2),
            torch.nn.GELU(),
            torch.nn.Linear(hidden2, 23),
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.model(state)


def state_vector(state: dict[str, Any]) -> np.ndarray:
    robot = state["robot"]
    return np.concatenate(
        [
            np.asarray(robot["root_pose"], dtype=np.float32).reshape(-1),
            np.asarray(robot["root_velocity"], dtype=np.float32).reshape(-1),
            np.asarray(robot["joint_position"], dtype=np.float32).reshape(-1),
            np.asarray(robot["joint_velocity"], dtype=np.float32).reshape(-1),
        ]
    )


def state_vector_from_rpc(state: dict[str, Any]) -> np.ndarray:
    return state_vector(state)


def action_groups(values: np.ndarray) -> dict[str, list[float]]:
    return {
        "grippers": values[:2].astype(float).tolist(),
        "wrists": values[2:16].astype(float).tolist(),
        "navigation": values[16:19].astype(float).tolist(),
        "base_height": values[19:20].astype(float).tolist(),
        "torso_rpy": values[20:23].astype(float).tolist(),
    }


def project_action(values: np.ndarray) -> np.ndarray:
    """Apply the simulator's basic gripper/quaternion action constraints."""
    result = np.asarray(values, dtype=np.float32).copy()
    result[~np.isfinite(result)] = 0.0
    result[:2] = np.clip(result[:2], -1.0, 1.0)
    for start in (5, 12):
        quat = result[start : start + 4]
        norm = float(np.linalg.norm(quat))
        result[start : start + 4] = (
            quat / norm
            if norm > 1e-6
            else np.asarray((1.0, 0.0, 0.0, 0.0), dtype=np.float32)
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--hdf5", type=Path, required=True)
    parser.add_argument("--demo", default="demo_1")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=50000, type=int)
    parser.add_argument("--authkey", default="lightwheel")
    parser.add_argument("--max-frames", type=int, default=300)
    parser.add_argument("--action-scale", type=float, default=1.0)
    parser.add_argument("--action-projection", choices=("safe", "none"), default="safe")
    args = parser.parse_args()
    if args.max_frames < 1:
        parser.error("--max-frames must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    actions, initial_state, expert_states, metadata = load_replay(args.hdf5, args.demo)
    total_frames = min(int(actions.shape[0]), args.max_frames)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(args.checkpoint, map_location=device, weights_only=False)
    state_mean = np.asarray(checkpoint["state_mean"], dtype=np.float32)
    state_std = np.asarray(checkpoint["state_std"], dtype=np.float32)
    action_mean = np.asarray(checkpoint["action_mean"], dtype=np.float32)
    action_std = np.asarray(checkpoint["action_std"], dtype=np.float32)
    history_length = int(checkpoint.get("history", 1))
    state_width = int(state_mean.shape[0] // history_length)
    first_weight = checkpoint["model_state_dict"]["model.0.weight"]
    second_weight = checkpoint["model_state_dict"]["model.2.weight"]
    model = ActionHead(
        int(state_mean.shape[0]),
        hidden1=int(first_weight.shape[0]),
        hidden2=int(second_weight.shape[0]),
    ).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    from robofinals.distributed.proxy import RemoteEnv
    from robofinals.distributed.restful import DotDict

    env = RemoteEnv.make(
        address=(args.host, args.port), authkey=args.authkey.encode("utf-8")
    )
    started = time.perf_counter()
    action_history: list[np.ndarray] = []
    pre_errors: list[dict[str, float]] = []
    post_errors: list[dict[str, float]] = []
    first_divergence: dict[str, Any] | None = None
    terminated_value = False
    truncated_value = False
    observation: Any = None

    try:
        atomic_json(
            {
                "status": "initializing",
                "phase": "attaching",
                "mode": "model_rollout",
                "checkpoint": str(args.checkpoint),
                "hdf5": str(args.hdf5),
                "demo": args.demo,
                "updated_unix": time.time(),
            },
            args.output_dir / "status.json",
        )
        config = make_ikea_config()
        env.attach(DotDict(config))
        atomic_json(
            {
                "status": "initializing",
                "phase": "resetting_to_demo_initial_state",
                "mode": "model_rollout",
                "demo": args.demo,
                "updated_unix": time.time(),
            },
            args.output_dir / "status.json",
        )
        env.reset()
        env._svc.set_initial_state(initial_state)
        # reset_to_state also refreshes RTX camera observations.  It is given
        # the same frame-0 state as set_initial_state, so this is not expert
        # action replay and does not advance the task.
        observation, _ = env._svc.reset_to_state(state_at(expert_states, 0))
        initial_actual = env._svc.scene_state_values()
        initial_error = trajectory_errors(initial_actual, expert_states, 0)
        state_history = [state_vector_from_rpc(initial_actual)] * history_length
        if divergence_reasons(initial_error):
            first_divergence = {
                "phase": "initial_state",
                "frame_index": 0,
                "reasons": divergence_reasons(initial_error),
                "errors": initial_error,
                "largest_joint_error": joint_divergence_detail(
                    initial_actual, expert_states, 0
                ),
            }

        for frame_index in range(total_frames):
            actual_state = env._svc.scene_state_values()
            pre_error = trajectory_errors(actual_state, expert_states, frame_index)
            pre_errors.append(pre_error)
            current_features = state_vector_from_rpc(actual_state)
            if current_features.shape[0] != state_width:
                raise RuntimeError(
                    f"single-state dimension mismatch: RPC={current_features.shape[0]} checkpoint_width={state_width}"
                )
            state_history[-1] = current_features
            features = np.concatenate(state_history, axis=0)
            if features.shape[0] != state_mean.shape[0]:
                raise RuntimeError(
                    f"state dimension mismatch: RPC={features.shape[0]} checkpoint={state_mean.shape[0]}"
                )
            state_tensor = torch.from_numpy(
                ((features - state_mean) / state_std).astype(np.float32)
            ).to(device)
            with torch.no_grad():
                normalized_action = model(state_tensor.unsqueeze(0))[0]
                predicted = (
                    normalized_action * torch.from_numpy(action_std).to(device)
                    + torch.from_numpy(action_mean).to(device)
                ).detach().cpu().numpy()
            raw_predicted = (predicted * args.action_scale).astype(np.float32)
            predicted = (
                project_action(raw_predicted)
                if args.action_projection == "safe"
                else raw_predicted
            )
            action_history.append(predicted.copy())
            observation, _, terminated, truncated, extras = env.step(
                torch.from_numpy(predicted[None]).to(device)
            )
            terminated_value = bool(to_numpy(terminated).any())
            truncated_value = bool(to_numpy(truncated).any())
            post_state = env._svc.scene_state_values()
            if history_length > 1:
                state_history = state_history[1:] + [state_vector_from_rpc(post_state)]
            compare_index = min(frame_index + 1, total_frames - 1)
            post_error = trajectory_errors(post_state, expert_states, compare_index)
            post_errors.append(post_error)
            reasons = divergence_reasons(post_error)
            if first_divergence is None and reasons:
                first_divergence = {
                    "phase": "post_action",
                    "frame_index": frame_index,
                    "expert_compare_frame": compare_index,
                    "reasons": reasons,
                    "errors": post_error,
                    "largest_joint_error": joint_divergence_detail(
                        post_state, expert_states, compare_index
                    ),
                }
            publish_frames(observation, args.output_dir)
            elapsed = time.perf_counter() - started
            atomic_json(
                {
                    "status": "running",
                    "mode": "model_rollout",
                    "demo": args.demo,
                    "frame_index": frame_index,
                    "completed_frames": frame_index + 1,
                    "total_frames": total_frames,
                    "dataset_total_frames": int(actions.shape[0]),
                    "progress_percent": 100.0 * (frame_index + 1) / total_frames,
                    "steps_per_second": (frame_index + 1) / elapsed if elapsed else 0.0,
                    "is_success": terminated_value,
                    "is_truncated": truncated_value,
                    "pre_action_error": pre_error,
                    "post_action_error": post_error,
                    "first_divergence": first_divergence,
                    "predicted_action": predicted.astype(float).tolist(),
                    "raw_predicted_action": raw_predicted.astype(float).tolist(),
                    "predicted_action_groups": action_groups(predicted),
                    "expert_action": actions[frame_index].astype(float).tolist(),
                    "expert_action_groups": action_groups(actions[frame_index]),
                    "updated_unix": time.time(),
                },
                args.output_dir / "status.json",
            )
            if terminated_value or truncated_value:
                break

        np.savez_compressed(
            args.output_dir.parent / "model_rollout_trace.npz",
            predicted_actions=np.asarray(action_history, dtype=np.float32),
            pre_joint_max_abs=np.asarray(
                [item["robot_joint_max_abs_rad"] for item in pre_errors], dtype=np.float32
            ),
            post_joint_max_abs=np.asarray(
                [item["robot_joint_max_abs_rad"] for item in post_errors], dtype=np.float32
            ),
        )
        final_error = post_errors[-1] if post_errors else initial_error
        report = {
            "status": "completed",
            "mode": "model_rollout",
            "checkpoint": str(args.checkpoint),
            "hdf5": str(args.hdf5),
            "demo": args.demo,
            "completed_frames": len(action_history),
            "requested_frames": total_frames,
            "dataset_total_frames": int(actions.shape[0]),
            "device": str(device),
            "action_scale": args.action_scale,
            "action_projection": args.action_projection,
            "history": history_length,
            "source_success": metadata["source_success"],
            "initial_state_error": initial_error,
            "first_divergence": first_divergence,
            "final_post_action_error": final_error,
            "max_post_action_errors": {
                name: float(max(item[name] for item in post_errors))
                for name in final_error
            }
            if post_errors
            else {},
            "terminated": terminated_value,
            "truncated": truncated_value,
            "elapsed_seconds": time.perf_counter() - started,
            "scope": "Short closed-loop predicted-action smoke rollout; no contact success claim.",
        }
        atomic_json(report, args.output_dir.parent / "model_rollout_report.json")
        atomic_json(
            {**report, "updated_unix": time.time()}, args.output_dir / "status.json"
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
    except Exception as exc:
        atomic_json(
            {
                "status": "error",
                "mode": "model_rollout",
                "message": f"{type(exc).__name__}: {exc}",
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
