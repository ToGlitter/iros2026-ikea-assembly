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
  's/execute_mode=ExecuteMode.EVAL,/execute_mode=str_to_execute_mode(getattr(cfg, "execute_mode", "eval")),/' \
  /workspace/robofinals/robofinals/scripts/env_server.py
sed -i \
  '/task_name = f"Robocasa-/i\        if getattr(cfg, "init_robot_base_pos", None) is not None:\
            env_cfg.scene.robot.init_state.pos = tuple(cfg.init_robot_base_pos)\
        # IKEA live viewer: keep the robot at the demonstrated task start pose.\
        env_cfg.scene.robot.init_state.pos = (-2.41, 2.4, 0.78)\
        env_cfg.scene.robot.init_state.rot = (0.0, 0.0, 0.0, 1.0)\
        env_cfg.isaaclab_arena_env.embodiment.scene_config.robot.init_state.pos = (-2.41, 2.4, 0.78)\
        env_cfg.isaaclab_arena_env.embodiment.scene_config.robot.init_state.rot = (0.0, 0.0, 0.0, 1.0)' \
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
\
    def set_initial_state(self, state):\
        import torch\
        env = self._env.unwrapped\
        robot = env.scene.articulations["robot"]\
        env_ids = torch.arange(robot.num_instances, device=env.device, dtype=torch.int32)\
        robot_state = state["robot"]\
        robot_pose = torch.tensor([robot_state["root_pose"]], device=env.device, dtype=torch.float32).repeat(robot.num_instances, 1)\
        robot_velocity = torch.tensor([robot_state["root_velocity"]], device=env.device, dtype=torch.float32).repeat(robot.num_instances, 1)\
        joint_position = torch.tensor([robot_state["joint_position"]], device=env.device, dtype=torch.float32).repeat(robot.num_instances, 1)\
        joint_velocity = torch.tensor([robot_state["joint_velocity"]], device=env.device, dtype=torch.float32).repeat(robot.num_instances, 1)\
        robot.write_root_pose_to_sim(robot_pose, env_ids=env_ids)\
        robot.write_root_velocity_to_sim(robot_velocity, env_ids=env_ids)\
        robot.write_joint_state_to_sim(joint_position, joint_velocity, env_ids=env_ids)\
        for name, object_state in state["rigid_objects"].items():\
            rigid_object = env.scene.rigid_objects[name]\
            root_pose = torch.tensor([object_state["root_pose"]], device=env.device, dtype=torch.float32).repeat(rigid_object.num_instances, 1)\
            root_velocity = torch.tensor([object_state["root_velocity"]], device=env.device, dtype=torch.float32).repeat(rigid_object.num_instances, 1)\
            rigid_object.write_root_pose_to_sim(root_pose, env_ids=env_ids)\
            rigid_object.write_root_velocity_to_sim(root_velocity, env_ids=env_ids)\
        env.sim.forward()\
        return True\
\
    def scene_state_values(self):\
        env = self._env.unwrapped\
        rigid_objects = {}\
        for name in env.scene.rigid_objects:\
            rigid_objects[name] = {\
                "root_pose": self.pose_values(f"scene.rigid_objects.{name}.data.root_pose_w"),\
                "root_velocity": self.pose_values(f"scene.rigid_objects.{name}.data.root_vel_w"),\
            }\
        return {\
            "robot": {\
                "joint_names": list(env.scene.articulations["robot"].joint_names),\
                "root_pose": self.pose_values("scene.articulations.robot.data.root_pose_w"),\
                "root_velocity": self.pose_values("scene.articulations.robot.data.root_vel_w"),\
                "joint_position": self.pose_values("scene.articulations.robot.data.joint_pos"),\
                "joint_velocity": self.pose_values("scene.articulations.robot.data.joint_vel"),\
            },\
            "rigid_objects": rigid_objects,\
        }\
\
    def reset_to_state(self, state):\
        import torch\
        env = self._env.unwrapped\
\
        def tensorize(value):\
            if isinstance(value, dict):\
                return {key: tensorize(item) for key, item in value.items()}\
            return torch.tensor(value, device=env.device, dtype=torch.float32)\
\
        env_ids = torch.tensor([0], device=env.device, dtype=torch.int32)\
        state_tensors = tensorize(state)\
        _, extras = env.reset_to(state_tensors, env_ids, is_relative=False)\
        # A state-only reset does not advance the Fabric physics-step counter.\
        # Pulse one physics dt so RTX consumes the new transforms, capture the\
        # cameras, then restore the exact expert state before returning.\
        env.sim.step(render=False)\
        env.sim.render_context.reset_transform_cadence()\
        env.scene.update(env.physics_dt)\
        observation = env.observation_manager.compute(update_history=False)\
        observation = _tensors_to_cpu(observation)\
        env.reset_to(state_tensors, env_ids, is_relative=False)\
        return observation, _tensors_to_cpu(extras)\
' \
  /workspace/robofinals/robofinals/distributed/proxy.py
sed -i \
  's/"call", "getattr_value"/"call", "pose_values", "set_robot_pose", "set_initial_state", "scene_state_values", "reset_to_state", "getattr_value"/' \
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
  --output-dir /host/logs/live \
  "$@"
