#!/usr/bin/env python3
"""Compare one official LeRobot episode with one Lightwheel HDF5 demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import h5py
from PIL import Image, ImageDraw


OFFICIAL_CAMERAS = ("cam_0", "cam_1", "cam_2", "cam_3")
LIGHTWHEEL_CAMERAS = (
    "first_person_camera_rgb",
    "left_hand_camera_rgb",
    "right_hand_camera_rgb",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compose_comparison(
    official_paths: list[Path],
    lightwheel_images: list[Any],
    labels: list[str],
    output: Path,
) -> None:
    tile_size = 224
    header_height = 28
    canvas = Image.new("RGB", (tile_size * 4, header_height * 2 + tile_size * 2), "black")
    draw = ImageDraw.Draw(canvas)
    draw.text((6, 6), "official LeRobot", fill="white")
    draw.text((6, header_height + 6), "Lightwheel HDF5", fill="white")

    for index, path in enumerate(official_paths):
        with Image.open(path) as image:
            canvas.paste(image.convert("RGB").resize((tile_size, tile_size)),
                        (index * tile_size, header_height))
    for index, image in enumerate(lightwheel_images):
        pil_image = Image.fromarray(image).convert("RGB").resize((tile_size, tile_size))
        canvas.paste(pil_image, (index * tile_size, header_height * 2 + tile_size))
    draw.text((tile_size * 4 - 190, 6), labels[0], fill="white")
    draw.text((tile_size * 4 - 190, header_height + 6), labels[1], fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=90)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-manifest", type=Path, required=True)
    parser.add_argument("--official-batch-report", type=Path, required=True)
    parser.add_argument("--official-image-dir", type=Path, required=True)
    parser.add_argument("--lightwheel-hdf5", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = load_json(args.official_manifest)
    official_batch = load_json(args.official_batch_report)
    official_episode = next(
        item for item in manifest["episodes"] if item["episode_index"] == 159
    )
    official_sample_by_frame = {
        int(item["frame_index"]): item for item in official_batch["samples"]
    }
    official_frames = [0, 4506, 9012]
    lightwheel_frames = [0, 3674, 7348]

    official_images = {}
    for frame in official_frames:
        official_images[frame] = [
            args.official_image_dir
            / f"episode-159_frame-{frame:05d}_{camera}.jpg"
            for camera in OFFICIAL_CAMERAS
        ]

    with h5py.File(args.lightwheel_hdf5, "r") as hdf5:
        demo = hdf5["data/demo_0"]
        env_args = json.loads(hdf5["data"].attrs["env_args"])
        lightwheel_length = int(demo.attrs["num_samples"])
        lightwheel_success = bool(demo.attrs["success"])
        actions_shape = list(demo["actions"].shape)
        image_shapes = {
            camera: list(demo[f"obs/{camera}"].shape)
            for camera in LIGHTWHEEL_CAMERAS
        }
        lightwheel_images = {}
        for frame in lightwheel_frames:
            lightwheel_images[frame] = [
                demo[f"obs/{camera}"][frame]
                for camera in LIGHTWHEEL_CAMERAS
            ]

        args.image_dir.mkdir(parents=True, exist_ok=True)
        comparisons = []
        for official_frame, lightwheel_frame in zip(official_frames, lightwheel_frames):
            output_image = args.image_dir / f"official159_vs_lightwheel_frame_{official_frame:05d}.jpg"
            compose_comparison(
                official_images[official_frame],
                lightwheel_images[lightwheel_frame],
                [f"frame {official_frame}", f"frame {lightwheel_frame}"],
                output_image,
            )
            comparisons.append(
                {
                    "official_frame": official_frame,
                    "lightwheel_frame": lightwheel_frame,
                    "image": str(output_image),
                }
            )

        camera_cfg = env_args.get("camera_cfg", {})
        action_definition = env_args.get("action_space_definition", [])
        simulation = env_args.get("sim_args", {})
        lightwheel_action_content = [
            item.get("action_content", []) for item in action_definition
        ]

    official_task_names = official_episode["tasks"]
    official_sample_tasks = {
        str(frame): {
            "task_index": official_sample_by_frame[frame]["task_index"],
            "task": official_sample_by_frame[frame]["task"],
        }
        for frame in official_frames
    }
    report = {
        "comparison": {
            "official_source": manifest["repo_id"],
            "official_episode": 159,
            "lightwheel_file": str(args.lightwheel_hdf5),
            "lightwheel_demo": "demo_0",
            "purpose": "single-demo schema, camera, timing, and action-space audit; not joint training",
        },
        "official": {
            "episode_length": official_episode["length"],
            "fps": manifest["fps"],
            "camera_count": len(OFFICIAL_CAMERAS),
            "camera_names": list(OFFICIAL_CAMERAS),
            "camera_shapes": official_batch["samples"][0]["images"],
            "task_labels": official_task_names,
            "sample_tasks": official_sample_tasks,
            "state_fields": [
                "observation.state.ee_state[12]",
                "observation.state.hand_state[2]",
                "observation.state.robot_q_current[36]",
            ],
            "action_fields": [
                "action.ee_action[12]",
                "action.hand_cmd[2]",
                "action.robot_q_desired[36]",
            ],
            "action_dimension": 50,
        },
        "lightwheel": {
            "episode_length": lightwheel_length,
            "simulation_dt": simulation.get("dt"),
            "decimation": simulation.get("decimation"),
            "control_hz": 1.0 / (float(simulation["dt"]) * int(simulation["decimation"])),
            "camera_count": len(LIGHTWHEEL_CAMERAS),
            "camera_names": list(LIGHTWHEEL_CAMERAS),
            "camera_shapes": image_shapes,
            "action_dimension": actions_shape[1],
            "action_shape": actions_shape,
            "action_definition": lightwheel_action_content,
            "success": lightwheel_success,
            "success_condition": env_args.get("success_condition"),
            "camera_config": camera_cfg,
        },
        "candidate_common_views": {
            "first_person": {
                "official": "cam_0 or cam_1 (head-view candidate; extrinsics not confirmed)",
                "lightwheel": "first_person_camera_rgb",
            },
            "left_hand": {
                "official": "cam_2 or cam_3 (hand-view candidate; side not confirmed)",
                "lightwheel": "left_hand_camera_rgb",
            },
            "right_hand": {
                "official": "cam_2 or cam_3 (hand-view candidate; side not confirmed)",
                "lightwheel": "right_hand_camera_rgb",
            },
            "decision": "Use three common-view inputs first; confirm official camera extrinsics before choosing cam_0..cam_3 mapping.",
        },
        "visual_comparisons": comparisons,
        "known_gaps": [
            "Official ee_action[12] TCP/frame and rotation encoding are not documented.",
            "Official 50D action and Lightwheel 23D action are not directly interchangeable.",
            "The two samples are not time-aligned demonstrations of the same physical execution.",
            "Official task_index labels need segment statistics before balanced sampling.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
