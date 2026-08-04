#!/usr/bin/env bash
set -Eeuo pipefail

steps="${1:-60}"
env_log=/host/logs/ikea_env_server.log
env_pid=""
export PYTHONPATH="/workspace/robofinals${PYTHONPATH:+:$PYTHONPATH}"

# RoboFinals-IKEA-V1 accepts this config field but env_server.py forgets to
# forward it to parse_env_cfg. Patch only the ephemeral container copy.
sed -i \
  '/physics_backend=getattr(cfg, "physics_backend", None),/a\            enable_full_local_scene=getattr(cfg, "enable_full_local_scene", False),' \
  /workspace/robofinals/robofinals/scripts/env_server.py
sed -i \
  '/task_name = f"Robocasa-/i\        if getattr(cfg, "init_robot_base_pos", None) is not None:\
            env_cfg.scene.robot.init_state.pos = tuple(cfg.init_robot_base_pos)' \
  /workspace/robofinals/robofinals/scripts/env_server.py
sed -i \
  '/for seg in path.split('\''.'\''):/a\            if isinstance(obj, dict):\
                obj = obj[seg]\
                continue' \
  /workspace/robofinals/robofinals/distributed/proxy.py

cleanup() {
  if [[ -n "$env_pid" ]] && kill -0 "$env_pid" 2>/dev/null; then
    kill "$env_pid" 2>/dev/null || true
    wait "$env_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

conda run --no-capture-output -n robofinals \
  python robofinals/scripts/env_server.py \
  --remote_protocol ipc \
  --ipc_host 127.0.0.1 \
  --ipc_port 50000 \
  --ipc_authkey lightwheel \
  --device cuda:0 \
  --headless \
  --livestream 1 \
  --enable_cameras \
  >"$env_log" 2>&1 &
env_pid=$!

/opt/conda/bin/python - <<'PY_WAIT'
import socket
import time

deadline = time.time() + 300
while time.time() < deadline:
    try:
        with socket.create_connection(("127.0.0.1", 50000), timeout=1):
            raise SystemExit(0)
    except OSError:
        time.sleep(1)
raise SystemExit("timeout waiting for env_server on 127.0.0.1:50000")
PY_WAIT

conda run --no-capture-output -n robofinals \
  python /host/scripts/ikea_smoke.py \
  --output /host/logs/ikea_smoke_result.json \
  --frames-dir /host/logs/ikea_smoke_frames \
  --steps "$steps"
