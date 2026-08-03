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
