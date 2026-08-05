#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_args=(run --rm
  --gpus all
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  -lc
  "conda run --no-capture-output -n openpi_robofinals_py312 python /host/scripts/train_official_state_baseline.py --data-file /host/datasets/official_lerobot/data/chunk-000/file-015.parquet --checkpoint /host/logs/official_state_baseline.pt --output /host/logs/official_state_baseline.json")

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi
