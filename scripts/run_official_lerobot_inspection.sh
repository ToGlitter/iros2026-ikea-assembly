#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dataset_root="${1:-$repo_root/datasets/official_lerobot}"
data_file="${2:-$dataset_root/data/chunk-000/file-015.parquet}"
output="${3:-$repo_root/logs/official_lerobot_sample.json}"

dataset_root="$(realpath "$dataset_root")"
data_file="$(realpath "$data_file")"
output="$(realpath -m "$output")"

for path in "$dataset_root/meta/info.json" "$dataset_root/meta/tasks.parquet" "$data_file"; do
  if [[ ! -f "$path" ]]; then
    printf 'Required official dataset file not found: %s\n' "$path" >&2
    exit 1
  fi
done

case "$dataset_root" in
  "$repo_root"/*) container_root="/host/${dataset_root#"$repo_root"/}" ;;
  *)
    printf 'Dataset root must be inside repository: %s\n' "$repo_root" >&2
    exit 1
    ;;
esac
case "$data_file" in
  "$repo_root"/*) container_data="/host/${data_file#"$repo_root"/}" ;;
  *)
    printf 'Data file must be inside repository: %s\n' "$repo_root" >&2
    exit 1
    ;;
esac
case "$output" in
  "$repo_root"/*) container_output="/host/${output#"$repo_root"/}" ;;
  *)
    printf 'Output must be inside repository: %s\n' "$repo_root" >&2
    exit 1
    ;;
esac

run_args=(run --rm
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  -lc
  "conda run --no-capture-output -n openpi_robofinals_py312 python /host/scripts/inspect_official_lerobot.py '$container_root' --data-file '$container_data' --output '$container_output'")

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi
