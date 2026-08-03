#!/usr/bin/env bash
set -u

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_file="${ROBOFINALS_PULL_LOG:-$repo_root/logs/robofinals-pull.log}"
attempt=1

mkdir -p "$(dirname "$log_file")"
exec >>"$log_file" 2>&1
printf '[%s] Starting pull for %s\n' "$(date -Is)" "$image"

until docker pull "$image"; do
  printf '[%s] Pull attempt %d failed; retrying in 15 seconds...\n' "$(date -Is)" "$attempt"
  attempt=$((attempt + 1))
  sleep 15
done

printf '[%s] Pull complete.\n' "$(date -Is)"
docker image inspect "$image" --format 'Digest={{index .RepoDigests 0}} Size={{.Size}}'
