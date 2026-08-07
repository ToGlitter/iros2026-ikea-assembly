#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

./scripts/run_official_first_stage_32_visual.sh 2>&1 \
  | tee logs/official_first_stage_32_visual.console.log
./scripts/run_lightwheel_first_stage_state_head.sh 2>&1 \
  | tee logs/lightwheel_first_stage_state_head.console.log
