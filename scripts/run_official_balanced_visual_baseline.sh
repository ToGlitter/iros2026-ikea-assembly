#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
steps="${OFFICIAL_BALANCED_VISUAL_STEPS:-5000}"
anchor_manifest="${OFFICIAL_BALANCED_ANCHOR_MANIFEST:-/host/logs/official_155_159_balanced_segments_160.json}"
validation_episode="${OFFICIAL_BALANCED_VALIDATION_EPISODE:-159}"

run_args=(run --rm
  --gpus all
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  -lc
  "conda run --no-capture-output -n openpi_robofinals_py312 python /host/scripts/train_official_visual_baseline.py --dataset-root /host/datasets/official_lerobot --manifest /host/logs/official_five_episode_manifest.json --anchor-manifest '$anchor_manifest' --cache /host/logs/official_balanced_visual_samples.npz --checkpoint /host/logs/official_balanced_visual_baseline_holdout_${validation_episode}.pt --output /host/logs/official_balanced_visual_baseline_holdout_${validation_episode}.json --steps '$steps' --validation-episode '$validation_episode'")

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi
