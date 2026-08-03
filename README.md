# IROS 2026 Humanoid IKEA Assembly

本仓库用于推进 IROS 2026 Humanoid IKEA Assembly Challenge：在仿真中建立可复现 baseline，并逐步迁移到 Unitree G1 + Dex1-1 的全自主 IKEA UTTER 儿童桌组装。

> 仓库不存放比赛镜像、HDF5 数据、模型权重、账号凭证或主办方未公开资产。

## 当前状态

| 项目 | 状态 |
| --- | --- |
| 比赛与数据入口 | 已确认 |
| RTX 4090 宿主机 | 已验证 |
| Docker + NVIDIA Container Toolkit | 已安装并通过 GPU 容器测试 |
| 官方镜像 | 后台下载中，自动重试 |
| 官方 OpenPI baseline | 已从镜像元数据确认，等待镜像完成后运行 |
| Lightwheel 完整任务数据 | 已确认 300 条 HDF5 仿真演示，尚未做 schema 审计 |
| 首次仿真 proof | 未完成 |

详细记录见 [docs/PROGRESS.md](docs/PROGRESS.md)。

## 官方资源

- Challenge: <https://humanoid-ikea-assembly-challenge.github.io/>
- 主办方数据: <https://huggingface.co/datasets/BitRobot/2026-humanoid-ikea-assembly-challenge>
- LeRobot 数据: <https://huggingface.co/datasets/BitRobot/G1_WBT_Dex1_Building-Children-Table>
- Lightwheel 完整任务数据: <https://huggingface.co/datasets/LightwheelAI/iros2026-ikea-assembly>
- 仿真镜像: `paperc/robofinals:RoboFinals-IKEA-V1`

## 查看镜像下载

下载由系统服务 `robofinals-pull.service` 执行。当前机器上可运行：

```bash
# 服务是否还在运行
systemctl status robofinals-pull.service --no-pager

# 持续查看下载/重试日志
tail -f /home/lumin/codexwork/robofinals-pull.log

# 镜像完整下载后，这条命令会显示镜像 ID 和大小
docker image ls paperc/robofinals:RoboFinals-IKEA-V1

# 显示 Docker 实际数据根目录
docker info --format '{{.DockerRootDir}}'
```

本机 Docker 数据根目录是 `/var/lib/docker`。镜像不是一个可以直接双击的单独文件，而是由 Docker 管理的内容寻址图层；不要手动编辑 `/var/lib/docker`。使用 `docker image ls`、`docker image inspect` 和 `docker system df` 查看即可。

仓库也提供统一状态命令：

```bash
./scripts/robofinals_status.sh
```

## 已确认的镜像内容

公开 OCI 配置显示镜像为 Linux/amd64，工作目录是 `/workspace/robofinals`，包含：

- Isaac Sim 6.0 和 IsaacLab-Arena
- `/workspace/robofinals`
- `/workspace/openpi`
- `/workspace/lerobot`
- `/workspace/Dexmal_Scene_Task`
- OpenPI 评测脚本 `docker/run_pi_eval_instance.sh`
- `49100/tcp` 与 `47998/udp`

镜像默认入口只是 `/bin/bash`，因此完整下载后必须先读取容器内 README 和脚本参数，不能凭空猜测启动参数。

## Baseline 路线

1. 完成官方镜像下载并核对 digest。
2. 以只读方式检查容器内 README、配置和 `run_pi_eval_instance.sh`。
3. 运行最小环境 reset 和保持动作，确认 observation/action 接口。
4. 运行镜像自带 OpenPI baseline，保存视频、日志、成功阶段与耗时。
5. 抽取一个 Lightwheel HDF5 样本，核对相机、状态、动作、单位和坐标系。
6. 建立 Lightwheel 到比赛环境的适配层。
7. 先做单技能闭环，再用状态机连接完整装桌流程。
8. 生成首次仿真策略运行证明。

## 仓库结构

```text
.
├── README.md
├── config/
│   └── docker-daemon.example.json
├── docs/
│   └── PROGRESS.md
├── logs/
│   └── README.md
└── scripts/
    ├── pull_robofinals.sh
    └── robofinals_status.sh
```

## 安全约束

- 仓库默认保持私有，确认可公开内容后再调整可见性。
- 不提交飞书/GitHub token、App Secret、代理订阅或主办方私发凭证。
- 不提交 `*.hdf5`、Docker 图层、模型 checkpoint 和大体积录像。
- 正式运行策略前确认动作类型、关节顺序、单位、控制频率与急停方式。
