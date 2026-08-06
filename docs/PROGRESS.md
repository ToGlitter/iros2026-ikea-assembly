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

### 挑战任务与八个官方技能

本挑战的目标不是只安装一条桌腿，而是由 Unitree G1 + Dex1-1 完成 IKEA UTTER 儿童桌的完整装配流程。官方演示覆盖以下八个技能标签：

1. `insert table leg to table base`：将桌腿插入桌面底座。
2. `move to table`：机器人移动到桌子附近。
3. `move table base`：移动桌面底座或调整其位置。
4. `flip table`：翻转桌面/桌面底座。
5. `rotate leg to tighten`：旋转桌腿完成拧紧。
6. `pick table leg`：抓取桌腿。
7. `rotate table base`：旋转桌面底座以便装配。
8. `building children table`：完成儿童桌组装的整体任务标签。

这些是行为技能名称，不应直接假设为连续的 task index 顺序；实际 index 以本地 `meta/tasks.parquet` 为准。一个 episode 是一次连续完整演示，不是一帧。

### 官方数据与 Lightwheel 数据的联合使用边界

- 官方 LeRobot 数据是主办方采集的真实机器人数据，包含四路 RGB 和 50 维状态/动作字段：`ee_action[12]`、`hand_cmd[2]`、`robot_q_desired[36]`。
- Lightwheel HDF5 是仿真演示数据，包含 Isaac Sim 状态、三路相机和已经对应仿真控制器的 23 维 action；300 条是数据集规模，本机目前只保留一条约 605 MB 的诊断样本。
- 两种数据可以用于同一个训练体系，但不能未经适配直接拼接。两者需要统一技能标签、相机分布、坐标系、夹爪范围、控制频率、action delay 和 TCP/frame 定义。
- 推荐分阶段使用：官方数据用于视觉/任务表示和动作趋势预训练，Lightwheel 数据用于 23 维 Isaac Sim 动作头、仿真状态和闭环微调。
- 在官方 `ee_action[12]` 的 TCP/frame 与旋转编码得到主办方确认前，不能伪造 50D→23D 映射，也不能把官方动作直接 replay 到 Isaac Sim。

### 截至本日的真实完成度

```text
仿真环境与网页查看器             已跑通
官方 Docker、GPU、Isaac Sim      已验证
官方 Parquet/RGB 数据读取        已跑通
官方 episodes 155–159            已下载并校验，共 48,755 帧
官方五条数据视觉 BC              已训练，并完成 episode 159 独立验证
Lightwheel 单条 state replay      已成功复现抓取和提腿状态
Lightwheel action replay          可完整执行，但最终 success=false
50D 官方动作到 23D 仿真动作       尚未完成
完整自主装桌策略                 尚未完成
```

当前 action replay 的首个明显偏差出现在 frame 76 的右肘关节，早于桌腿在 frame 186 的显著运动。因此首要待查项是 action 解析、WBC、低层控制频率/延迟和归一化，而不是先假定 PhysX 接触求解器出错。

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

### 五条官方演示视觉 BC

- 选择并下载 episodes 155–159，共 48,755 帧、约 1.5 GB；五条均覆盖 8 个官方任务标签。
- 完整扫描两份 Parquet，目标 episode 行数与 metadata 一致，六组状态/动作向量均为有限数值。
- 建立下载 manifest、四路 RGB 解码缓存和紧凑视觉 + proprioception 行为克隆训练脚本。
- 每条演示均匀采样 256 帧，共 1,280 个样本；每个样本包含四路 `64 × 64` RGB、50 维 proprioception、任务 one-hot，目标为官方 50 维原始动作。
- 五条轨迹内随机留出 10% 的 5,000 步实验：训练归一化 MSE `0.0173`，验证 MSE `0.1056`，但该划分可能受相邻帧相似性影响。
- 严格 leave-one-episode-out 实验只用 155–158 的 1,024 个样本训练，把 159 的 256 个样本完整留作验证：训练归一化 MSE `0.0152`，验证 MSE `0.1608`。
- 独立验证 RMSE：`ee_action 0.0817`、`hand_cmd 0.2806`、`robot_q_desired 0.0366 rad`。夹爪命令是当前最明显短板。
- checkpoint 和详细 JSON 只保存在本地 `logs/`，本轮未同步 GitHub。

### 五条训练后的下一步

1. 加入短时序输入和 action chunk，避免单帧模型无法辨别动作阶段，并改善夹爪开合预测。
2. 对 8 个任务阶段做采样平衡和逐技能指标，确认误差集中在哪些装配阶段。
3. TCP 定义确认后建立显式 23 维 Isaac Sim 策略头，先在无接触短 rollout 验收坐标系、动作范围和控制频率。
4. 通过短 rollout 后再进入接触抓取闭环；官方 50 维原始动作不能直接送入 23 维仿真接口。

### 短时序与 action chunk 实验

- 新增 `scripts/train_official_temporal_baseline.py` 和对应 Docker 启动脚本。
- 每个样本使用 `[-6, -4, -2, 0]` 四个历史时刻，覆盖 30 FPS 下约 0.2 秒；共享 CNN 编码四路 RGB，GRU 聚合视觉、50 维 proprioception 和任务标签。
- 每个锚点预测当前开始连续 8 帧、每帧 50 维的官方动作，action chunk 覆盖约 0.267 秒。
- 视频使用 Parquet timestamp 加 manifest `from_timestamp` 定位共享 MP4 内的 episode 片段，从目标前 2 秒关键帧开始顺序解码；最大时间误差约 14 微秒。
- 直接动作版训练 MSE `0.0139`、独立验证 MSE `0.2478`；首步 RMSE 为末端 `0.0959`、夹爪 `0.3432`、关节 `0.0415 rad`，没有超过单帧 baseline。
- 残差版改为相对当前 50 维状态预测动作，并让末端、夹爪、关节三组归一化损失等权。独立验证首步 RMSE 为末端 `0.1039`、夹爪 `0.1245`、关节 `0.0266 rad`。
- 相比单帧 baseline，残差时序版夹爪改善约 56%、关节改善约 27%，但末端误差增加约 27%。因此不能声称时序模型整体胜出。
- 8 步完整 chunk 的独立验证 RMSE 为末端 `0.1113`、夹爪 `0.1857`、关节 `0.0403 rad`。
- 另测“末端直接预测、夹爪和关节残差预测”的混合目标；首步 RMSE 为末端 `0.1122`、夹爪 `0.1263`、关节 `0.0247 rad`。仅关节略有改善，末端进一步退化，因此不作为默认模型。

### 时序实验结论

1. 夹爪与关节适合相对当前状态的残差目标；末端在现有五条数据上仍以原单帧直接模型最好。混合目标实验没有同时保住三组指标。
2. 五条数据足以验证训练设计，但不足以证明长任务泛化；扩大数据前先补逐技能指标和阶段平衡采样。
3. 时序模型仍输出官方 50 维动作，必须等 TCP/frame 定义明确后再接 23 维 Isaac Sim 策略头。
