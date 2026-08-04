#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_log="$repo_root/logs/ikea_env_server.log"
result_json="$repo_root/logs/ikea_smoke_result.json"
frames_dir="$repo_root/logs/ikea_smoke_frames"
steps="${IKEA_SMOKE_STEPS:-60}"

mkdir -p "$repo_root/logs"

run_args=(run --rm
  --name robofinals-ikea-smoke
  --gpus all
  --ipc=host
  --network=host
  --shm-size=16g
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  /host/scripts/ikea_smoke_container.sh
  "$steps")

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi

printf 'Environment log: %s\n' "$env_log"
printf 'Smoke result: %s\n' "$result_json"
printf 'Camera frames: %s\n' "$frames_dir"
