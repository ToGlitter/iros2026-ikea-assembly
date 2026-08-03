#!/usr/bin/env bash
set -u

image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
service="${ROBOFINALS_PULL_SERVICE:-robofinals-pull.service}"
host_log="${ROBOFINALS_PULL_LOG:-/home/lumin/codexwork/robofinals-pull.log}"

printf 'Service: '
systemctl is-active "$service" 2>/dev/null || true

printf '\nDocker root:\n'
docker info --format '{{.DockerRootDir}}' 2>/dev/null || true

printf '\nImage:\n'
docker image ls "$image"

if [[ -f "$host_log" ]]; then
  printf '\nRecent pull log (%s):\n' "$host_log"
  tail -n 25 "$host_log"
fi
