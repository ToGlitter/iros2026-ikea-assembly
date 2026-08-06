#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
steps="${OFFICIAL_TEMPORAL_STEPS:-3000}"
samples_per_episode="${OFFICIAL_TEMPORAL_SAMPLES_PER_EPISODE:-256}"
batch_size="${OFFICIAL_TEMPORAL_BATCH_SIZE:-32}"
validation_episode="${OFFICIAL_TEMPORAL_VALIDATION_EPISODE:-159}"
target_mode="${OFFICIAL_TEMPORAL_TARGET_MODE:-residual}"

run_args=(run --rm
  --gpus all
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  -lc
  "conda run --no-capture-output -n openpi_robofinals_py312 python /host/scripts/train_official_temporal_baseline.py --dataset-root /host/datasets/official_lerobot --manifest /host/logs/official_five_episode_manifest.json --cache /host/logs/official_temporal_samples_h4_c8.npz --checkpoint /host/logs/official_temporal_${target_mode}_baseline_holdout_${validation_episode}.pt --output /host/logs/official_temporal_${target_mode}_baseline_holdout_${validation_episode}.json --steps '$steps' --samples-per-episode '$samples_per_episode' --batch-size '$batch_size' --validation-episode '$validation_episode' --target-mode '$target_mode'")

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi
