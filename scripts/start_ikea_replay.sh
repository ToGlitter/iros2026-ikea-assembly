#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dataset="${1:-$repo_root/datasets/AssembleTableTask_1784627181912351.hdf5}"
demo="${IKEA_REPLAY_DEMO:-demo_0}"
dataset="$(realpath "$dataset")"

if [[ ! -f "$dataset" ]]; then
  printf 'Replay dataset not found: %s\n' "$dataset" >&2
  exit 1
fi

case "$dataset" in
  "$repo_root"/*) container_dataset="/host/${dataset#"$repo_root"/}" ;;
  *)
    printf 'Replay dataset must be inside repository: %s\n' "$repo_root" >&2
    exit 1
    ;;
esac

mkdir -p "$repo_root/logs/live"
rm -f \
  "$repo_root/logs/live/left_hand_camera_rgb.jpg" \
  "$repo_root/logs/live/first_person_camera_rgb.jpg" \
  "$repo_root/logs/live/right_hand_camera_rgb.jpg" \
  "$repo_root/logs/live/status.json"

if docker info >/dev/null 2>&1; then
  docker rm -f robofinals-ikea-live robofinals-ikea-replay >/dev/null 2>&1 || true
  docker run --detach \
    --name robofinals-ikea-replay \
    --gpus all \
    --ipc=host \
    --network=host \
    --shm-size=16g \
    --volume "$repo_root:/host" \
    --entrypoint /bin/bash \
    "$image" \
    /host/scripts/ikea_live_container.sh \
    --replay-hdf5 "$container_dataset" \
    --demo "$demo"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker rm -f robofinals-ikea-live robofinals-ikea-replay
  sg docker -c "$docker_command" >/dev/null 2>&1 || true
  run_args=(run --detach
    --name robofinals-ikea-replay
    --gpus all
    --ipc=host
    --network=host
    --shm-size=16g
    --volume "$repo_root:/host"
    --entrypoint /bin/bash
    "$image"
    /host/scripts/ikea_live_container.sh
    --replay-hdf5 "$container_dataset"
    --demo "$demo")
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi

"$repo_root/scripts/start_ikea_viewer.sh"
printf 'Replay container: robofinals-ikea-replay\n'
printf 'Viewer: http://127.0.0.1:8765/viewer/\n'
