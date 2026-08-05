#!/usr/bin/env python3
"""Compare official 6D end-effector fields with FK from the 36D robot target."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pinocchio as pin
import pyarrow.parquet as pq
from scipy.spatial.transform import Rotation


BODY_JOINTS = (
    "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint",
    "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
    "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint",
    "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
    "waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint",
    "left_shoulder_pitch_joint", "left_shoulder_roll_joint", "left_shoulder_yaw_joint",
    "left_elbow_joint", "left_wrist_roll_joint", "left_wrist_pitch_joint",
    "left_wrist_yaw_joint", "right_shoulder_pitch_joint", "right_shoulder_roll_joint",
    "right_shoulder_yaw_joint", "right_elbow_joint", "right_wrist_roll_joint",
    "right_wrist_pitch_joint", "right_wrist_yaw_joint",
)


def fk(model: pin.Model, data: pin.Data, root_and_body: np.ndarray, frame_name: str) -> tuple[np.ndarray, np.ndarray]:
    q = pin.neutral(model)
    q[:3] = root_and_body[:3]
    q[3:7] = root_and_body[3:7][[1, 2, 3, 0]]  # source wxyz -> Pinocchio xyzw
    for value, joint_name in zip(root_and_body[7:], BODY_JOINTS):
        joint_id = model.getJointId(joint_name)
        q[model.idx_qs[joint_id]] = value
    pin.forwardKinematics(model, data, q)
    pin.updateFramePlacements(model, data)
    frame_id = model.getFrameId(frame_name)
    placement = data.oMf[frame_id]
    return np.asarray(placement.translation), np.asarray(placement.rotation)


def error_metrics(pred: np.ndarray, target: np.ndarray) -> dict[str, float]:
    return {
        "mean_abs": float(np.mean(np.abs(pred - target))),
        "max_abs": float(np.max(np.abs(pred - target))),
        "rmse": float(np.sqrt(np.mean((pred - target) ** 2))),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-file", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--episode-index", type=int, default=159)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    model = pin.buildModelFromUrdf(str(args.urdf), pin.JointModelFreeFlyer())
    data = model.createData()
    frame_names = [frame.name for frame in model.frames]
    candidates = [
        name
        for name in frame_names
        if any(token in name.lower() for token in ("wrist", "hand", "palm"))
    ]
    rows = pq.read_table(
        args.data_file,
        columns=[
            "episode_index",
            "observation.state.ee_state",
            "observation.state.robot_q_current",
            "action.ee_action",
            "action.robot_q_desired",
        ],
    ).to_pylist()
    rows = [row for row in rows if int(row["episode_index"]) == args.episode_index]
    if not rows:
        raise KeyError(f"episode {args.episode_index} not found")
    rows = rows[:: max(1, len(rows) // 100)]

    records = []
    offsets = {
        "rpy": {"left": [], "right": []},
        "rotvec": {"left": [], "right": []},
    }
    for row in rows:
        for field_name, robot_key, ee_key in (
            ("state", "observation.state.robot_q_current", "observation.state.ee_state"),
            ("action", "action.robot_q_desired", "action.ee_action"),
        ):
            robot = np.asarray(row[robot_key], dtype=np.float64)
            target = np.asarray(row[ee_key], dtype=np.float64).reshape(2, 6)
            for side, side_name in enumerate(("left", "right")):
                position, rotation = fk(model, data, robot, f"{side_name}_wrist_yaw_link")
                root_position = robot[:3]
                root_rotation = Rotation.from_quat(robot[3:7][[1, 2, 3, 0]]).as_matrix()
                root_relative_position = root_rotation.T @ (position - root_position)
                root_relative_rotation = root_rotation.T @ rotation
                rpy = pin.rpy.matrixToRpy(rotation)
                rotvec = Rotation.from_matrix(rotation).as_rotvec()
                root_rpy = pin.rpy.matrixToRpy(root_relative_rotation)
                root_rotvec = Rotation.from_matrix(root_relative_rotation).as_rotvec()
                if field_name == "state":
                    for encoding, target_rotation in (
                        ("rpy", pin.rpy.rpyToMatrix(target[side, 3:])),
                        ("rotvec", Rotation.from_rotvec(target[side, 3:]).as_matrix()),
                    ):
                        offset_position = root_relative_rotation.T @ (
                            target[side, :3] - root_relative_position
                        )
                        offset_rotation = root_relative_rotation.T @ target_rotation
                        offsets[encoding][side_name].append(
                            np.r_[
                                offset_position,
                                Rotation.from_matrix(offset_rotation).as_rotvec(),
                            ]
                        )
                records.append(
                    {
                        "field": field_name,
                        "side": side_name,
                        "target": target[side].tolist(),
                        "fk_world": np.r_[position, rpy].tolist(),
                        "fk_root": np.r_[root_relative_position, root_rpy].tolist(),
                        "fk_world_rotvec": np.r_[position, rotvec].tolist(),
                        "fk_root_rotvec": np.r_[root_relative_position, root_rotvec].tolist(),
                    }
                )

    hypotheses = {}
    for frame_key in ("fk_world", "fk_root", "fk_world_rotvec", "fk_root_rotvec"):
        values = [error_metrics(np.asarray(record[frame_key]), np.asarray(record["target"])) for record in records]
        hypotheses[frame_key] = {
            "mean_abs": float(np.mean([value["mean_abs"] for value in values])),
            "max_abs": float(np.max([value["max_abs"] for value in values])),
            "rmse": float(np.sqrt(np.mean([value["rmse"] ** 2 for value in values]))),
        }
    grouped_hypotheses = {}
    for field_name in ("state", "action"):
        grouped_hypotheses[field_name] = {}
        selected = [record for record in records if record["field"] == field_name]
        for frame_key in ("fk_root", "fk_root_rotvec"):
            pred = np.asarray([record[frame_key] for record in selected])
            target = np.asarray([record["target"] for record in selected])
            grouped_hypotheses[field_name][frame_key] = error_metrics(pred, target)
    offset_consistency = {}
    for encoding, by_side in offsets.items():
        offset_consistency[encoding] = {}
        for side_name, values in by_side.items():
            array = np.asarray(values)
            offset_consistency[encoding][side_name] = {
                "mean_xyz_rotvec": np.mean(array, axis=0).tolist(),
                "std_xyz_rotvec": np.std(array, axis=0).tolist(),
                "max_std": float(np.max(np.std(array, axis=0))),
            }
    report = {
        "urdf": str(args.urdf),
        "model_nq": model.nq,
        "model_nv": model.nv,
        "frame_candidates": candidates,
        "tested_rows": len(rows),
        "tested_fields": ["observation.state.ee_state", "action.ee_action"],
        "hypotheses_for_left_right_wrist_yaw_link": hypotheses,
        "hypotheses_by_field": grouped_hypotheses,
        "state_tcp_offset_consistency": offset_consistency,
        "first_records": records[:4],
        "note": "A low error identifies the pose convention; high error means the official endpoint frame or joint ordering needs another source of metadata.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
