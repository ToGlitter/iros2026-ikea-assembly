#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
checkpoint="${LIGHTWHEEL_ROLLOUT_CHECKPOINT:-/host/logs/lightwheel_first_stage_state_head.pt}"
hdf5="${LIGHTWHEEL_ROLLOUT_HDF5:-/host/datasets/lightwheel_first_stage/data/AssembleTableTask_1784697887866010.hdf5}"
demo="${LIGHTWHEEL_ROLLOUT_DEMO:-demo_1}"
frames="${LIGHTWHEEL_ROLLOUT_FRAMES:-300}"
output="${LIGHTWHEEL_ROLLOUT_OUTPUT:-/host/logs/lightwheel_model_rollout}"
projection="${LIGHTWHEEL_ROLLOUT_ACTION_PROJECTION:-safe}"
rate_limit="${LIGHTWHEEL_ROLLOUT_RATE_LIMIT:-checkpoint}"
rate_scale="${LIGHTWHEEL_ROLLOUT_RATE_LIMIT_SCALE:-1.0}"
ensemble_decay="${LIGHTWHEEL_ROLLOUT_ENSEMBLE_DECAY:-0.25}"

run_args=(run --rm
  --gpus all
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  -lc
  "bash /host/scripts/ikea_live_container.sh --model-rollout --checkpoint '$checkpoint' --hdf5 '$hdf5' --demo '$demo' --max-frames '$frames' --action-projection '$projection' --rate-limit '$rate_limit' --rate-limit-scale '$rate_scale' --temporal-ensemble-decay '$ensemble_decay' --output-dir '$output'"
)

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi
