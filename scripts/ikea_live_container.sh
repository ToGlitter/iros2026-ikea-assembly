#!/usr/bin/env bash
set -Eeuo pipefail

env_log=/host/logs/ikea_live_env_server.log
env_pid=""
export PYTHONPATH="/workspace/robofinals:/host/scripts${PYTHONPATH:+:$PYTHONPATH}"

cleanup() {
  if [[ -n "$env_pid" ]] && kill -0 "$env_pid" 2>/dev/null; then
    kill "$env_pid" 2>/dev/null || true
    wait "$env_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

sed -i \
  '/physics_backend=getattr(cfg, "physics_backend", None),/a\            enable_full_local_scene=getattr(cfg, "enable_full_local_scene", False),' \
  /workspace/robofinals/robofinals/scripts/env_server.py
sed -i \
  '/task_name = f"Robocasa-/i\        if getattr(cfg, "init_robot_base_pos", None) is not None:\
            env_cfg.scene.robot.init_state.pos = tuple(cfg.init_robot_base_pos)\
        # IKEA live viewer: keep the robot at the demonstrated task start pose.\
        env_cfg.scene.robot.init_state.pos = (-2.41, 2.4, 0.78)\
        env_cfg.scene.robot.init_state.rot = (0.0, 0.0, 0.0, 1.0)' \
  /workspace/robofinals/robofinals/scripts/env_server.py
sed -i \
  '/for seg in path.split('\''.'\''):/a\            if isinstance(obj, dict):\
                obj = obj[seg]\
                continue' \
  /workspace/robofinals/robofinals/distributed/proxy.py
sed -i \
  '/    def getattr_value(self, path: str):/i\    def pose_values(self, path: str):\
        value = self._resolve(path)\
        value = getattr(value, "tensor", value)\
        if hasattr(value, "detach"):\
            value = value.detach()\
        if hasattr(value, "cpu"):\
            value = value.cpu()\
        if hasattr(value, "numpy"):\
            value = value.numpy()\
        return value.tolist() if hasattr(value, "tolist") else list(value)\
\
    def set_robot_pose(self, pose):\
        import torch\
        env = self._env.unwrapped\
        robot = env.scene.articulations["robot"]\
        env_ids = torch.arange(robot.num_instances, device=env.device, dtype=torch.int32)\
        root_pose = torch.tensor([pose], device=env.device, dtype=torch.float32).repeat(robot.num_instances, 1)\
        robot.write_root_pose_to_sim(root_pose=root_pose, env_ids=env_ids)\
        env.sim.forward()\
        return True\
' \
  /workspace/robofinals/robofinals/distributed/proxy.py
sed -i \
  's/"call", "getattr_value"/"call", "pose_values", "set_robot_pose", "getattr_value"/' \
  /workspace/robofinals/robofinals/distributed/proxy.py

conda run --no-capture-output -n robofinals \
  python robofinals/scripts/env_server.py \
  --remote_protocol ipc \
  --ipc_host 127.0.0.1 \
  --ipc_port 50000 \
  --ipc_authkey lightwheel \
  --device cuda:0 \
  --headless \
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
  python /host/scripts/ikea_live.py \
  --output-dir /host/logs/live
