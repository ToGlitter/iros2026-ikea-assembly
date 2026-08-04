#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit="iros-ikea-viewer.service"

if systemctl --user is-active --quiet "$unit"; then
  printf 'Viewer service is already running.\n'
else
  systemctl --user reset-failed "$unit" >/dev/null 2>&1 || true
  systemd-run --user --collect \
    --unit=iros-ikea-viewer \
    --working-directory="$repo_root" \
    /usr/bin/python3 -m http.server 8765 --bind 127.0.0.1
fi

printf 'Viewer: http://127.0.0.1:8765/viewer/\n'
