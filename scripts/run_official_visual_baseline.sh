#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
steps="${OFFICIAL_VISUAL_STEPS:-1000}"
samples_per_episode="${OFFICIAL_VISUAL_SAMPLES_PER_EPISODE:-256}"
validation_episode="${OFFICIAL_VISUAL_VALIDATION_EPISODE:-}"
output_suffix=""
validation_arg=""
if [[ -n "$validation_episode" ]]; then
  output_suffix="_holdout_${validation_episode}"
  validation_arg="--validation-episode '$validation_episode'"
fi

run_args=(run --rm
  --gpus all
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  -lc
  "conda run --no-capture-output -n openpi_robofinals_py312 python /host/scripts/train_official_visual_baseline.py --dataset-root /host/datasets/official_lerobot --manifest /host/logs/official_five_episode_manifest.json --cache /host/logs/official_visual_samples.npz --checkpoint /host/logs/official_visual_baseline${output_suffix}.pt --output /host/logs/official_visual_baseline${output_suffix}.json --steps '$steps' --samples-per-episode '$samples_per_episode' $validation_arg")

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi
