#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data_file="/host/datasets/official_lerobot/data/chunk-000/file-015.parquet"
output="/host/logs/official_ee_encoding.json"
urdf="/workspace/robofinals/robofinals/data/assets/g1_urdf_gripper/g1/g1_29dof_mode_15_with_dex1_1.urdf"

run_args=(run --rm
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  -lc
  "conda run --no-capture-output -n openpi_robofinals_py312 python /host/scripts/analyze_official_ee_encoding.py --data-file '$data_file' --urdf '$urdf' --output '$output'")

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi
