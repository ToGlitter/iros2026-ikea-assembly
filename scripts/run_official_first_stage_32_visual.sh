#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
steps="${OFFICIAL_FIRST_STAGE_STEPS:-5000}"
samples="${OFFICIAL_FIRST_STAGE_SAMPLES_PER_EPISODE:-256}"

run_args=(run --rm
  --gpus all
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  -lc
  "conda run --no-capture-output -n openpi_robofinals_py312 python /host/scripts/train_official_visual_baseline.py --dataset-root /host/datasets/official_lerobot --manifest /host/logs/official_first_stage_32_manifest.json --cache /host/logs/official_first_stage_32_visual_samples.npz --checkpoint /host/logs/official_first_stage_32_visual.pt --output /host/logs/official_first_stage_32_visual.json --steps '$steps' --samples-per-episode '$samples' --validation-episodes 159 300 420 532 --test-episodes 100 250 400 500")

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi
