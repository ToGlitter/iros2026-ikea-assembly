#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$repo_root/logs/live"
rm -f \
  "$repo_root/logs/live/left_hand_camera_rgb.jpg" \
  "$repo_root/logs/live/first_person_camera_rgb.jpg" \
  "$repo_root/logs/live/right_hand_camera_rgb.jpg" \
  "$repo_root/logs/live/status.json"

run_args=(run --detach
  --name robofinals-ikea-live
  --gpus all
  --ipc=host
  --network=host
  --shm-size=16g
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  /host/scripts/ikea_live_container.sh)

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi

printf 'Live simulation container: robofinals-ikea-live\n'
printf 'Frames: %s\n' "$repo_root/logs/live"
if ! "$repo_root/scripts/start_ikea_viewer.sh"; then
  printf 'Viewer service could not be started automatically.\n' >&2
  printf 'Run: python3 -m http.server 8765 --bind 127.0.0.1\n' >&2
fi
