#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dataset="${1:-$repo_root/datasets/AssembleTableTask_1784627181912351.hdf5}"
demo="${IKEA_STATE_REPLAY_DEMO:-demo_0}"
# An explicitly empty value means replay the complete demo. Only an unset
# variable keeps the short 600-frame default.
max_frames="${IKEA_STATE_REPLAY_MAX_FRAMES-600}"
dataset="$(realpath "$dataset")"

if [[ ! -f "$dataset" ]]; then
  printf 'State replay dataset not found: %s\n' "$dataset" >&2
  exit 1
fi

case "$dataset" in
  "$repo_root"/*) container_dataset="/host/${dataset#"$repo_root"/}" ;;
  *)
    printf 'State replay dataset must be inside repository: %s\n' "$repo_root" >&2
    exit 1
    ;;
esac

mkdir -p "$repo_root/logs/live"
rm -f \
  "$repo_root/logs/live/left_hand_camera_rgb.jpg" \
  "$repo_root/logs/live/first_person_camera_rgb.jpg" \
  "$repo_root/logs/live/right_hand_camera_rgb.jpg" \
  "$repo_root/logs/live/status.json"

max_frame_args=()
if [[ -n "$max_frames" ]]; then
  max_frame_args=(--max-frames "$max_frames")
fi

containers=(
  robofinals-ikea-live
  robofinals-ikea-replay
  robofinals-ikea-state-replay
)

if docker info >/dev/null 2>&1; then
  docker rm -f "${containers[@]}" >/dev/null 2>&1 || true
  docker run --detach \
    --name robofinals-ikea-state-replay \
    --gpus all \
    --ipc=host \
    --network=host \
    --shm-size=16g \
    --volume "$repo_root:/host" \
    --entrypoint /bin/bash \
    "$image" \
    /host/scripts/ikea_live_container.sh \
    --state-replay-hdf5 "$container_dataset" \
    --demo "$demo" \
    "${max_frame_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker rm -f "${containers[@]}"
  sg docker -c "$docker_command" >/dev/null 2>&1 || true
  run_args=(run --detach
    --name robofinals-ikea-state-replay
    --gpus all
    --ipc=host
    --network=host
    --shm-size=16g
    --volume "$repo_root:/host"
    --entrypoint /bin/bash
    "$image"
    /host/scripts/ikea_live_container.sh
    --state-replay-hdf5 "$container_dataset"
    --demo "$demo"
    "${max_frame_args[@]}")
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi

"$repo_root/scripts/start_ikea_viewer.sh"
printf 'State replay container: robofinals-ikea-state-replay\n'
printf 'Viewer: http://127.0.0.1:8765/viewer/\n'
