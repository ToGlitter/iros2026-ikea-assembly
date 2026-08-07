#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
run_args=(run --rm
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  -lc
  "conda run --no-capture-output -n robofinals python /host/scripts/compare_official_lightwheel_single_demo.py --official-manifest /host/logs/official_five_episode_manifest.json --official-batch-report /host/logs/official_lerobot_batch.json --official-image-dir /host/logs/official_lerobot_batch_frames --lightwheel-hdf5 /host/datasets/AssembleTableTask_1784627181912351.hdf5 --output /host/logs/official159_lightwheel_demo0_comparison.json --image-dir /host/logs/official159_lightwheel_comparison_frames")

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi
