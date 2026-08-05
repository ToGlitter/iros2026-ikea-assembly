# IROS 2026 Humanoid IKEA Assembly

本仓库用于推进 IROS 2026 Humanoid IKEA Assembly Challenge：在官方 Isaac Sim 环境中建立可复现 baseline，并逐步实现 Unitree G1 + Dex1-1 全自主组装 IKEA UTTER 儿童桌。

> 仓库不存放比赛 Docker 镜像、HDF5 数据、模型权重、账号凭证或主办方未公开资产。

## 当前状态

| 项目 | 状态 |
| --- | --- |
| 官方 Docker 镜像 | 已完整下载并核对 digest |
| RTX 4090 + NVIDIA Container Toolkit | 已验证 |
| Isaac Sim / AssembleTableTask | 已成功启动 |
| Lightwheel HDF5 样本 | 已下载一条并完成 schema 审计 |
| 23 维动作协议 | 已确认 |
| Neutral hold baseline | 60/60 步成功 |
| 三路相机实时画面 | 已完成 |
| 完整演示动作重放 | 7349/7349 已跑通，`success=false` |
| 官方 state replay | 已接入并验证抓取，关键状态误差为 0 |
| 动作重放偏差定位 | frame 76 关节先偏离，早于 frame 186 物体运动 |
| 官方 OpenPI baseline | 待运行 |

详细记录见 [docs/PROGRESS.md](docs/PROGRESS.md)。

## 已验证环境

- 镜像：`paperc/robofinals:RoboFinals-IKEA-V1`
- 镜像 digest：`sha256:3751591c01648702b759892f36ee473b5acb5d7d69844df09d44991b5d123448`
- Task：`AssembleTableTask`
- Robot：`G1-Gripper-Controller-DecoupledWBC`
- Scene：`/workspace/IROS_IKEA_V13_20260702/Scene02.usd`
- Action dimension：23
- Simulation dt：0.005 s
- Decimation：4，即控制周期约 0.02 s（50 Hz）
- Camera：第一人称、左手、右手，均为 224 × 224 RGB

## 快速开始

前提：Docker 能访问 NVIDIA GPU，且本机已有官方镜像。

### 1. 运行最小 baseline

```bash
./scripts/run_ikea_smoke.sh
```

输出仅保存在本地：

```text
logs/ikea_env_server.log
logs/ikea_smoke_result.json
logs/ikea_smoke_frames/
```

默认执行 60 步 neutral hold，可通过环境变量改变步数：

```bash
IKEA_SMOKE_STEPS=300 ./scripts/run_ikea_smoke.sh
```

### 2. 启动实时仿真画面

```bash
./scripts/start_ikea_live.sh
```

浏览器访问：

<http://127.0.0.1:8765/viewer/>

网页自动刷新三路相机，并显示 step、FPS 和错误状态。首次加载 Isaac Sim 通常需要 1–3 分钟；页面会先显示 `initializing`。

查看容器和实时状态：

```bash
docker ps --filter name=robofinals-ikea-live
cat logs/live/status.json
docker logs -f robofinals-ikea-live
```

停止实时仿真和网页服务：

```bash
docker rm -f robofinals-ikea-live
systemctl --user stop iros-ikea-viewer.service
```

### 3. 审计 HDF5 演示

将样本放入 `datasets/` 后运行：

```bash
./scripts/run_hdf5_inspection.sh datasets/AssembleTableTask_*.hdf5
```

报告默认写入 `logs/hdf5_schema.json`。数据和报告均被 `.gitignore` 排除，避免提交大文件或内部元数据。

### 4. 对比两种专家重放

动作重放会把 23 维专家 action 重新交给 WBC 和 PhysX，适合验证控制闭环：

```bash
./scripts/start_ikea_replay.sh datasets/AssembleTableTask_1784627181912351.hdf5
```

官方 state replay 逐帧恢复 HDF5 中的机器人和刚体状态，适合验证数据、场景和成功轨迹：

```bash
./scripts/start_ikea_state_replay.sh datasets/AssembleTableTask_1784627181912351.hdf5
```

state replay 默认播放前 600 帧。播放完整 7349 帧：

```bash
IKEA_STATE_REPLAY_MAX_FRAMES= ./scripts/start_ikea_state_replay.sh datasets/AssembleTableTask_1784627181912351.hdf5
```

两种模式都使用 <http://127.0.0.1:8765/viewer/>。状态栏会明确显示 `replay` 或 `state replay`，并显示当前帧、百分比和 FPS。

## 23 维动作协议

```text
0       left gripper open degree
1       right gripper open degree
2:9     left wrist pose: x y z qw qx qy qz
9:16    right wrist pose: x y z qw qx qy qz
16:19   navigation velocity: x y yaw
19      base height
20:23   torso roll pitch yaw
```

全零动作不是合法保持动作，因为左右腕四元数的范数为零。当前 neutral hold 使用已验证演示的首帧动作，定义在 `scripts/ikea_smoke.py`。

## 已完成 baseline 结果

- 60/60 步完成，无 terminated/truncated。
- 约 13.8 step/s。
- 夹爪最大漂移约 `5.5e-6`。
- 关节位置最大漂移约 `0.07 rad`。
- 末端位置最大漂移约 `2.4 cm`。
- 实时仿真中机器人已放置到演示起点，桌面和待装配零件可见。
- 首轮完整 open-loop replay 执行 7349/7349 帧，约 13.2 step/s，无异常终止或截断，但最终 `success=false`。
- action replay 首个显著偏差出现在 frame 76：`right_elbow_joint` 误差约 `0.227 rad`。
- 专家轨迹中首个桌腿 `Leg001_01` 到 frame 186 才移动超过 1 cm；frame 202 超过 3 cm，frame 403 位移达到约 0.777 m。
- 官方 state replay 在 frame 0/160/180/187/202/220/300/403 的机器人和全部刚体位置误差均为 0，画面可见夹取和提起桌腿。
- 因为关节偏差早于物体运动约 110 帧，当前首要问题是 action 到 WBC/关节跟踪链路；接触与 PhysX 求解会在偏差产生后继续放大误差，但不是第一个原因。

实时查看器包含对官方镜像临时容器副本的兼容补丁：转发完整本地场景参数、支持字典形式的远程对象路径，并在 reset 后恢复演示中的机器人根位姿。不会修改宿主机上的 Docker 镜像。

## 下一阶段路线

1. 在无物体接触条件下重放前 186 帧，记录 WBC 目标、关节目标和实际关节，隔离控制跟踪误差。
2. 核对数据采集时与当前镜像的 WBC checkpoint、action delay、控制频率和归一化配置。
3. 在控制跟踪对齐后恢复接触，比较 PhysX TGS 参数、接触力和夹爪约束。
4. 运行镜像自带 OpenPI baseline，建立第二条官方对照线。
5. 将 Lightwheel 300 条完整演示转换为训练索引，先训练行为克隆/ACT 类策略。
6. 按“抓腿—对孔—插入—释放—换腿”拆成单技能闭环，再用状态机完成整桌。

## 官方资源

- Challenge: <https://humanoid-ikea-assembly-challenge.github.io/>
- 主办方数据: <https://huggingface.co/datasets/BitRobot/2026-humanoid-ikea-assembly-challenge>
- LeRobot 数据: <https://huggingface.co/datasets/BitRobot/G1_WBT_Dex1_Building-Children-Table>
- Lightwheel 数据: <https://huggingface.co/datasets/LightwheelAI/iros2026-ikea-assembly>
- 仿真镜像: `paperc/robofinals:RoboFinals-IKEA-V1`

## 仓库结构

```text
.
├── README.md
├── config/
├── docs/
│   └── PROGRESS.md
├── logs/
│   └── README.md
├── scripts/
│   ├── inspect_hdf5.py
│   ├── analyze_expert_states.py
│   ├── diagnose_replay.py
│   ├── ikea_live.py
│   ├── ikea_smoke.py
│   ├── run_hdf5_inspection.sh
│   ├── run_ikea_smoke.sh
│   ├── start_ikea_live.sh
│   ├── start_ikea_replay.sh
│   └── start_ikea_state_replay.sh
└── viewer/
    └── index.html
```

## 安全约束

- 不提交飞书/GitHub token、App Secret、代理订阅或私发凭证。
- 不提交 `*.hdf5`、Docker 图层、checkpoint 和大体积录像。
- 正式运行策略前确认动作顺序、单位、控制频率、坐标系和急停方式。
