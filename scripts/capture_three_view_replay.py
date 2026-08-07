#!/usr/bin/env python3
"""Capture the live viewer's three camera JPEGs into numbered composite frames."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from PIL import Image, ImageDraw, UnidentifiedImageError


CAMERAS = (
    ("first_person_camera_rgb.jpg", "first person"),
    ("left_hand_camera_rgb.jpg", "left hand"),
    ("right_hand_camera_rgb.jpg", "right hand"),
)


def read_status(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def compose(input_dir: Path, status: dict, output: Path) -> bool:
    images = []
    try:
        for filename, _ in CAMERAS:
            with Image.open(input_dir / filename) as image:
                images.append(image.convert("RGB").resize((224, 224)))
    except (FileNotFoundError, UnidentifiedImageError, OSError):
        return False

    canvas = Image.new("RGB", (672, 264), (10, 10, 10))
    for index, image in enumerate(images):
        canvas.paste(image, (index * 224, 40))
    draw = ImageDraw.Draw(canvas)
    frame = status.get("frame_index", "-")
    completed = status.get("completed_frames", "-")
    total = status.get("total_frames", "-")
    progress = status.get("progress_percent", 0.0)
    mode = status.get("mode", "state_replay")
    draw.text(
        (8, 10),
        f"{mode} | frame {frame} | {completed}/{total} | {float(progress):.1f}%",
        fill=(255, 255, 255),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=88, optimize=True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=0.03)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    last_frame = -1
    written = 0
    saw_running = False
    started = time.time()
    while True:
        status = read_status(args.status)
        if status.get("status") == "running" and status.get("mode") == "state_replay":
            saw_running = True
        frame = status.get("frame_index")
        if isinstance(frame, int) and frame != last_frame:
            if compose(args.input_dir, status, args.output_dir / f"frame_{written:06d}.jpg"):
                last_frame = frame
                written += 1
        if saw_running and status.get("status") in {"completed", "failed", "error"}:
            completed_frames = status.get("completed_frames")
            if isinstance(completed_frames, int) and completed_frames > 0:
                final_frame = completed_frames - 1
                if final_frame != last_frame:
                    final_status = dict(status)
                    final_status["frame_index"] = final_frame
                    if compose(
                        args.input_dir,
                        final_status,
                        args.output_dir / f"frame_{written:06d}.jpg",
                    ):
                        last_frame = final_frame
                        written += 1
            break
        time.sleep(args.poll_seconds)

    summary = {
        "frames_written": written,
        "last_replay_frame": last_frame,
        "elapsed_seconds": time.time() - started,
    }
    (args.output_dir / "capture_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
