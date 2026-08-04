#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  printf 'Usage: %s DATASET.hdf5\n' "$0" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
input="$(realpath "$1")"
case "$input" in
  "$repo_root"/*) ;;
  *)
    printf 'Input must be inside %s so it can be mounted read-only.\n' "$repo_root" >&2
    exit 2
    ;;
esac

relative_input="${input#"$repo_root"/}"
output="$repo_root/logs/hdf5_schema.json"
image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
run_args=(run --rm
  --volume "$repo_root:/host"
  --entrypoint /opt/conda/bin/conda
  "$image"
  run -n robofinals python /host/scripts/inspect_hdf5.py
  "/host/$relative_input"
  --output /host/logs/hdf5_schema.json)

if docker info >/dev/null 2>&1; then
  docker "${run_args[@]}"
elif getent group docker | grep -q "$(id -un)"; then
  printf -v docker_command '%q ' docker "${run_args[@]}"
  sg docker -c "$docker_command"
else
  printf 'Cannot access Docker. Log out and back in to refresh docker group membership.\n' >&2
  exit 1
fi

printf 'Schema report: %s\n' "$output"
