# 项目进展日志

## 2026-08-03

### 比赛入口与目标

- 确认挑战目标为 Unitree G1 + Dex1-1 全自主组装 IKEA UTTER 儿童桌。
- 确认首次提交可使用真机录像，或仿真中策略有效运行的证明。
- 确认 Docker 镜像 ID：`paperc/robofinals:RoboFinals-IKEA-V1`。
- 公开比赛网站未发现单独 SDK；开发接口位于比赛镜像内部。

### 官方镜像审计

- 平台：`linux/amd64`。
- OCI index digest：`sha256:3751591c01648702b759892f36ee473b5acb5d7d69844df09d44991b5d123448`。
- amd64 manifest digest：`sha256:b28f8f0572936b8802dffa0f0224a4fd21038829b064cf8354cdb8eb29e8dd74`。
- Docker Hub 报告镜像大小约 `111,888,668,419` 字节。
- 默认入口：`/bin/bash`；工作目录：`/workspace/robofinals`。
- 确认包含 Isaac Sim 6.0、IsaacLab-Arena、OpenPI、LeRobot 和比赛代码。
- 确认存在 `docker/run_pi_eval_instance.sh`，官方镜像自带 OpenPI baseline。
- 暴露端口：`49100/tcp`、`47998/udp`。

### 本机环境

- Ubuntu 22.04，x86_64。
- NVIDIA GeForce RTX 4090，24 GB 显存，驱动 595.84。
- 安装 Docker Engine 29.1.3。
- 安装 NVIDIA Container Toolkit 1.19.1。
- 使用 Ubuntu 22.04 小型容器成功执行 `nvidia-smi`，GPU 透传通过。
- Docker 数据根目录：`/var/lib/docker`。
- 为不稳定网络配置 6 路并发和失败自动重试。
- 建立后台服务 `robofinals-pull.service` 拉取比赛镜像。

### 数据资产

- 主办方 LeRobot 数据：533 episodes、约 627 万帧、30 FPS、8 类技能。
- Lightwheel 数据：300 条完整 `AssembleTableTask_*.hdf5` 仿真演示。
- Lightwheel 数据逻辑总量约 262.5 GB；计划先检查约 606 MB 的最小样本，不做全量盲目下载。
- 尚未确认 Lightwheel observation/action schema 与比赛 Docker 接口是否一致。

### 协作工具

- 安装 Node.js 22.23.2。
- 安装并登录飞书 CLI 1.0.81。
- 安装 27 个飞书官方 Agent Skill。
- 飞书 CLI doctor 检查全部通过。

### 当前进行中

- `paperc/robofinals:RoboFinals-IKEA-V1` 正在后台拉取。
- Docker Hub 链路存在低速和 EOF；服务会自动重试。

### 下一步验收条件

- `docker image inspect paperc/robofinals:RoboFinals-IKEA-V1` 成功。
- 读取镜像内 README 和 `docker/run_pi_eval_instance.sh` 的真实参数。
- 启动仿真并完成一次 reset。
- 运行官方 OpenPI baseline 并生成可复现日志/录像。
- 下载单个 Lightwheel HDF5 样本并输出 schema 报告。

## 2026-08-04

### 官方镜像与 GPU 仿真

- 官方镜像 `paperc/robofinals:RoboFinals-IKEA-V1` 已完整下载。
- 核对 digest：`sha256:3751591c01648702b759892f36ee473b5acb5d7d69844df09d44991b5d123448`。
- RTX 4090、NVIDIA Container Toolkit、Isaac Sim 6.0 和相机渲染均已实际运行验证。
- 确认任务组合：
  - Task：`AssembleTableTask`
  - Robot：`G1-Gripper-Controller-DecoupledWBC`
  - Scene：`/workspace/IROS_IKEA_V13_20260702/Scene02.usd`
  - Action dimension：23
  - Decimation：4

### Lightwheel HDF5 审计

- 下载样本：`AssembleTableTask_1784627181912351.hdf5`。
- 文件大小：605,895,638 bytes，SHA-256：`7eb9674f10800b56a458755195dff216b9ee0df88091f3e7514a32db0724d94f`。
- 样本包含一条成功演示，共 7349 帧。
- 确认三路 224 × 224 RGB 相机、机器人/刚体状态、初始状态、checkpoint 和 23 维动作。
- 成功条件记录为：所有桌腿插入区域与桌板对应区域 XY 距离不超过 0.030 m，并且两只夹爪与所有桌腿距离大于 0.250 m、无显著接触力。
- 新增 `scripts/inspect_hdf5.py` 与 `scripts/run_hdf5_inspection.sh`，结构化报告保存在本地 `logs/hdf5_schema.json`。

### 动作协议

- 确认动作顺序为：左右夹爪 2 维、左右腕位姿各 7 维、导航速度 3 维、基座高度 1 维、躯干 RPY 3 维，共 23 维。
- 动作中的腕部四元数顺序为 `qw qx qy qz`。
- 根位姿通过 Warp/场景接口读取和写入时使用 `xyzw`；这与动作腕部四元数顺序不同，适配器必须显式转换。
- 全零动作会产生 zero-norm quaternion 错误，不能作为保持动作。

### Neutral hold smoke baseline

- 新增：
  - `scripts/ikea_smoke.py`
  - `scripts/ikea_smoke_container.sh`
  - `scripts/run_ikea_smoke.sh`
- 使用 Lightwheel 演示首帧作为合法 neutral hold 动作。
- 60/60 步完成，无 terminated/truncated，速度约 13.8 step/s。
- 夹爪最大漂移约 `5.5e-6`，关节最大漂移约 `0.07 rad`，末端最大漂移约 `2.4 cm`。
- 三路相机帧和结构化结果保存在本地 `logs/`，不提交 GitHub。

### 实时三相机查看器

- 新增：
  - `scripts/ikea_live.py`
  - `scripts/ikea_live_container.sh`
  - `scripts/start_ikea_live.sh`
  - `scripts/start_ikea_viewer.sh`
  - `viewer/index.html`
- 浏览器地址：<http://127.0.0.1:8765/viewer/>。
- 页面每 150 ms 刷新第一人称、左手、右手相机，并显示初始化、运行、FPS 和错误状态。
- 排查并修复了以下问题：
  - 官方 `env_server.py` 未完整转发 `enable_full_local_scene`。
  - 远程代理默认不能解析 `scene.articulations["robot"]` 一类字典路径。
  - 静态机器人出生点会被 reset 流程覆盖。
  - 根位姿的 Warp 接口使用 `xyzw`，与动作腕部 `wxyz` 约定不同。
  - Warp CUDA 位姿对象不能直接通过 manager IPC 序列化，需要在仿真进程转为 CPU list。
- 当前机器人稳定处于演示起点附近，三路相机能够看到桌板、四条桌腿和桌边结构。

### 当前结论

- 已从“镜像下载”推进到“任务环境可运行、动作接口已知、数据可解析、画面可实时观察”。
- 当前 neutral hold 是接口和稳定性 baseline，不是装桌策略，不产生 success。
- Lightwheel 数据与官方镜像的任务、机器人、相机和动作维度高度一致，是后续训练与轨迹重放的主要优势。

### 下一步验收条件

1. 完整重放一条 7349 帧成功演示，并生成视频及 success 判定。
2. 对比重放轨迹和 HDF5 中机器人/桌腿状态，输出误差曲线。
3. 审计并运行镜像自带 OpenPI baseline，保存统一格式结果。
4. 为 300 条 Lightwheel 演示建立训练 manifest，不下载或提交无关大文件。

### 首轮完整专家动作重放

- 新增 `scripts/start_ikea_replay.sh`，复用实时三相机网页显示 HDF5 replay。
- replay 前恢复 HDF5 中记录的机器人根位姿、关节位置/速度、桌板及四条桌腿根位姿/速度。
- 完整执行 `demo_0` 的 7349/7349 帧动作。
- 平均速度约 13.2 step/s，无异常退出、terminated 或 truncated。
- 页面实时显示 `frame/total`、完成百分比、FPS 和 success。
- 最终 `success=false`：开环动作可以驱动双臂和导航，但没有在当前仿真中复现演示的成功终态。
- 这一结果将下一步问题收敛为“专家状态轨迹与 replay 实际状态的逐帧偏差”，而不是环境、动作维度或相机链路故障。

下一轮将记录机器人和所有桌腿的逐帧实际状态，对齐 HDF5 `states/`，找出首个显著偏离的帧和对象。
