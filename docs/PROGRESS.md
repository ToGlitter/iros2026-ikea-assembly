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

### Action replay 逐帧诊断

- 新增实际状态采集、误差曲线和 `scripts/diagnose_replay.py`。
- 600 帧对齐结果显示，首个显著偏差出现在 frame 76：
  - 关节：`right_elbow_joint`
  - 实际值：约 `-0.041 rad`
  - 专家值：约 `-0.267 rad`
  - 误差：约 `0.227 rad`
- 专家右夹爪 action 在 frame 187 从 `-1`（打开）切换为 `+1`（关闭）。
- `Leg001_01` 专家状态在 frame 186 首次移动超过 1 cm，frame 202 超过 3 cm，frame 403 最大位移约 0.777 m。
- 将 seed 从 42 对齐为 HDF5 的 0，并在构建期/reset 后对齐机器人出生点，首个偏差仍不变。
- 官方源码确认夹爪符号为 `-1 = open`、`+1 = close`。
- 排除 seed、机器人出生点和夹爪符号作为首要原因。

### 官方 state replay 对照

- 审计镜像内 `robofinals/scripts/teleop/replay_demos.py`，确认官方 replay 使用 `ExecuteMode.REPLAY_STATE` 和 `env.reset_to(next_state, ..., is_relative=False)`，不是重新执行 actions。
- 新增：
  - `scripts/start_ikea_state_replay.sh`
  - `scripts/analyze_expert_states.py`
  - state replay RPC、网页状态显示、关键帧和写入后状态误差核验
- 600 帧 state replay 完整执行，源演示 `success=true`。
- frame 160/187/202/300/403 画面确认机器人接近、夹住并提起第一根桌腿。
- frame 0/160/180/187/202/220/300/403 的机器人根姿态、关节位置和全部刚体位置误差均为 0；四元数误差仅有约 `3e-8` 至 `5e-8 rad` 的浮点噪声。
- 该镜像的 Fabric/RTX transform 更新按 physics step 去重，而纯 `reset_to` 不推进 step。网页渲染因此使用一次 0.005 s 物理 pulse 刷新 Fabric，抓取画面后立即恢复同一专家状态；恢复后的状态继续通过零误差核验。

### 当前归因

- HDF5 专家状态、Scene02 资产和官方 state replay 链路正确，可以复现真实抓取。
- action replay 在预期物体接触前约 110 帧已经出现 0.227 rad 关节误差，因此首要问题位于 action 到 WBC/关节跟踪链路，而不是接触求解器。
- 物体姿态在 frame 167 开始异常，说明偏离后的非预期接触会继续放大误差；PhysX/TGS 接触参数仍需检查，但应放在 WBC 跟踪对齐之后。

### 下一步验收条件

1. 在禁用桌腿碰撞或移走桌腿的环境中执行前 186 帧 action，确认右肘偏差是否仍在 frame 76 出现。
2. 记录每帧 WBC 输入、关节目标和实际关节，定位误差产生于 action 解析、WBC 输出还是低层 PD/求解。
3. 对比演示采集和当前镜像的 WBC checkpoint、控制频率、action delay、归一化与滤波配置。
4. 控制轨迹对齐后恢复接触，记录夹爪接触力并比较 PhysX TGS 参数。

## 2026-08-05

### Baseline 数据源切换

- 当前训练主线切换为主办方官方数据 `BitRobot/G1_WBT_Dex1_Building-Children-Table`。
- Lightwheel HDF5 暂时退出 baseline 输入，只保留为仿真 state replay 与控制链路诊断对照。
- 不拉取 374 GB 全库，先选 episode 159 建立端到端最小数据链路。

### 官方最小样本

- 下载 `data/chunk-000/file-015.parquet`，大小 4,843,547 bytes。
- episode 159 共 9,013 帧，30 FPS，约 300.4 秒，覆盖全部 8 个官方任务标签。
- 状态/动作字段为 `ee_state[12]`、`hand_state[2]`、`robot_q_current[36]`、`ee_action[12]`、`hand_cmd[2]`、`robot_q_desired[36]`；全部数值有限。
- 下载该 episode 引用的四个 RGB 文件，共 340,483,407 bytes；没有下载四路 IR 或其余 episode。
- 四路 RGB 均为 H.264、640 × 480、30 FPS。抽帧显示 `cam_0/1` 为近似双目头部视角，`cam_2/3` 为手部近景；精确左右命名仍需采集配置确认。

### Loader 验证

- 新增官方 v3 Parquet 检查器、按 episode 断点续传 RGB 的下载器，以及 PyArrow + PyAV 最小 batch loader。
- 实际加载 episode 159 的 frame 0、4506、9012，每帧同时读取四路 RGB 和六组状态/动作向量。
- 解码图像形状均为 `[480, 640, 3]`，视频时间戳误差为 0 到约 6.1 微秒。
- 比赛镜像内 LeRobot 版本为 `0.1.0`，其原生 loader 期望 `tasks.jsonl`，与官方数据的 v3 Parquet 元数据不兼容；当前最小 loader 已绕开该依赖冲突。

### 接口边界

- 官方 36 维真机配置由根位置 3、根四元数 `wxyz` 4 和 29 个关节组成。
- 官方手指命令范围为 `5.5（张开）` 到 `0（闭合）`。
- 官方数据集卡没有给出 `ee_action[12]` 的旋转编码，不能未经确认转换为仿真腕部四元数。
- Isaac Sim 接收 23 维高层动作，不接受 36 维真机关节目标；官方数据可以用于策略训练，但不能直接作为仿真 state replay。

### 下一步验收条件

1. 从主办方采集配置确认 12 维末端姿态编码和四路相机名称。
2. 建立官方 v3 数据的训练 adapter 与按技能采样器。
3. 在少量官方 episode 上跑通 IKEA 专用策略的 overfit smoke test。
4. 增加 23 维仿真策略头并在 Isaac Sim 做闭环评估。

### FK 编码审计与训练 smoke

- 新增 `scripts/analyze_official_ee_encoding.py`，在官方镜像内使用 G1 URDF + Pinocchio 对官方 `ee_state/ee_action` 做 FK 对照。
- 36 维官方关节目标与镜像 URDF 的 29 个身体关节顺序一致：根位姿 7 + 腿 12 + 腰 3 + 双臂 14。
- 根坐标系解释明显优于世界坐标系；对 `left/right_wrist_yaw_link` 的根坐标 RPY 假设平均绝对误差约 `0.053`，旋转向量约 `0.082`。
- 仍存在约厘米级位置和 0.1 rad 级 TCP 偏移/姿态误差，说明采集端末端 frame 与仿真 URDF wrist link 不是同一 frame；暂不把这个结果当作 23 维控制映射。
- 新增 `scripts/train_official_state_baseline.py`，将官方 36/12/2 维原始字段组成 58 维 state+task 输入和 50 维动作目标。
- episode 159 前 2,048 帧训练 500 步：归一化训练 MSE `1.003 -> 0.0564`，验证 MSE `0.0742`，`robot_q_desired` 验证 RMSE `0.0137 rad`，checkpoint 仅保存在本机 `logs/`。
- 该 smoke baseline 验证的是“官方数据 -> adapter -> 优化器 -> checkpoint”，没有声明视觉闭环或 Isaac Sim 成功。

### 当前下一步

1. 获取主办方采集端 TCP/frame 定义，消除 FK 审计中的末端偏移。
2. 加入四路 RGB 输入，做 episode 159 图像条件 overfit。
3. 再实现显式的 23 维仿真策略头，并用 Lightwheel state replay/Isaac Sim 做闭环验收。
