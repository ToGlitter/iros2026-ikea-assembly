#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
pythonpath="${PYTHONPATH:-}"
if [[ -d /tmp/ikea-pydeps ]]; then
  pythonpath="/tmp/ikea-pydeps${pythonpath:+:${pythonpath}}"
fi

export PYTHONPATH="$pythonpath"
episodes=( $(seq 0 532) )
"$python_bin" "$repo_root/scripts/plan_official_episodes.py" \
  "$repo_root/datasets/official_lerobot" \
  --episodes "${episodes[@]}" \
  --output "$repo_root/logs/official_all_episode_manifest.json" >/dev/null
"$python_bin" "$repo_root/scripts/analyze_official_task_segments.py" \
  "$repo_root/datasets/official_lerobot" \
  --manifest "$repo_root/logs/official_all_episode_manifest.json" \
  --output "$repo_root/logs/official_all_task_segments.json" >/dev/null
printf 'Wrote %s and %s\n' \
  "$repo_root/logs/official_all_episode_manifest.json" \
  "$repo_root/logs/official_all_task_segments.json"
