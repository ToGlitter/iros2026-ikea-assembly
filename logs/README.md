# Runtime logs

本目录用于本地运行日志。原始日志默认被 `.gitignore` 排除；需要长期保留的结论应整理到 `docs/PROGRESS.md`，避免提交巨大或包含敏感信息的日志文件。

本地运行会产生：

- `hdf5_schema.json`：HDF5 schema、统计量和抽样值。
- `ikea_smoke_result.json`：smoke rollout 指标。
- `ikea_smoke_frames/`：smoke 起止相机帧。
- `live/`：实时查看器相机帧和状态。
- `replay_errors.npz`、`replay_comparison.json`：action replay 逐帧误差。
- `expert_state_analysis.json`：专家轨迹中的机器人/刚体运动区间。
- `state_replay_verification.json`：state replay 写入后的关键帧状态误差。
- `official_lerobot_sample.json`：官方 Parquet 样本的 schema、episode 索引和向量统计。
- `official_lerobot_batch.json`：官方 episode 159 的图像/状态/动作 batch 验证。
- `official_lerobot_batch_frames/`：batch 验证解码的四路 RGB 抽帧。
- `official_ee_encoding.json`：官方末端字段与 G1 URDF FK 的编码/坐标系对照。
- `official_state_baseline.json`、`official_state_baseline.pt`：官方 state-only BC smoke 指标和本地 checkpoint。
- `*.log`：Isaac Sim / env server 日志。

这些文件可能很大，或含内部数据路径和元数据，因此不会同步到 GitHub。
