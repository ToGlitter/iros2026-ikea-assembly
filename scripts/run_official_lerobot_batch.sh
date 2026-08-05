#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dataset_root="$repo_root/datasets/official_lerobot"
data_file="$dataset_root/data/chunk-000/file-015.parquet"
metadata_file="$dataset_root/meta/episodes/chunk-000/file-008.parquet"
output="$repo_root/logs/official_lerobot_batch.json"
image_dir="$repo_root/logs/official_lerobot_batch_frames"

for path in "$data_file" "$metadata_file"; do
  if [[ ! -f "$path" ]]; then
    printf 'Required official dataset file not found: %s\n' "$path" >&2
    exit 1
  fi
done

run_args=(run --rm
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  -lc
  "conda run --no-capture-output -n openpi_robofinals_py312 python /host/scripts/load_official_lerobot_batch.py /host/datasets/official_lerobot --data-file /host/datasets/official_lerobot/data/chunk-000/file-015.parquet --metadata-file /host/datasets/official_lerobot/meta/episodes/chunk-000/file-008.parquet --output /host/logs/official_lerobot_batch.json --image-dir /host/logs/official_lerobot_batch_frames")

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi
