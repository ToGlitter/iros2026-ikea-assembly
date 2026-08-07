#!/usr/bin/env bash
set -Eeuo pipefail

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
steps="${LIGHTWHEEL_STATE_HEAD_STEPS:-5000}"
samples="${LIGHTWHEEL_STATE_HEAD_SAMPLES_PER_DEMO:-512}"

run_args=(run --rm
  --gpus all
  --volume "$repo_root:/host"
  --entrypoint /bin/bash
  "$image"
  -lc
  "conda run --no-capture-output -n robofinals python /host/scripts/train_lightwheel_state_action_head.py --dataset-root /host/datasets/lightwheel_first_stage --selection /host/logs/first_stage_experiment_selection.json --checkpoint /host/logs/lightwheel_first_stage_state_head.pt --output /host/logs/lightwheel_first_stage_state_head.json --steps '$steps' --samples-per-demo '$samples'")

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi
