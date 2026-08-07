#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dataset="${1:-$repo_root/datasets/AssembleTableTask_1784627181912351.hdf5}"
output="${2:-$repo_root/ikea_state_replay_three_view.mp4}"
image="${ROBOFINALS_IMAGE:-paperc/robofinals:RoboFinals-IKEA-V1}"
capture_dir="/tmp/ikea_three_view_capture"

rm -rf "$capture_dir"
mkdir -p "$capture_dir"

python3 "$repo_root/scripts/capture_three_view_replay.py" \
  --input-dir "$repo_root/logs/live" \
  --status "$repo_root/logs/live/status.json" \
  --output-dir "$capture_dir" &
capture_pid=$!

cleanup() {
  if kill -0 "$capture_pid" 2>/dev/null; then
    kill "$capture_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

IKEA_STATE_REPLAY_MAX_FRAMES= \
  "$repo_root/scripts/start_ikea_state_replay.sh" "$dataset"
wait "$capture_pid"

case "$repo_root" in
  /home/*|/tmp/*) ;;
  *) printf 'Unexpected repository path: %s\n' "$repo_root" >&2; exit 1 ;;
esac

output_name="$(basename "$output")"
ffmpeg_args=(run --rm
  --volume "$repo_root:/host"
  --volume "$capture_dir:/frames:ro"
  --entrypoint /usr/bin/ffmpeg
  "$image"
  -hide_banner -loglevel error -y
  -framerate 10 -i /frames/frame_%06d.jpg
  -c:v libx264 -preset fast -crf 20 -pix_fmt yuv420p
  "/host/$output_name")
printf -v docker_command '%q ' docker "${ffmpeg_args[@]}"
sg docker -c "$docker_command"

rm -rf "$capture_dir"
printf 'Three-view replay video: %s\n' "$output"
