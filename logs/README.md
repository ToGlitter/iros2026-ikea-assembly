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
- `official_five_episode_manifest.json`：episodes 155–159 的 Parquet 与四路 RGB 文件规划。
- `official_visual_samples.npz`：五条演示均匀采样后的本地视觉训练缓存。
- `official_visual_baseline.json`、`official_visual_baseline.pt`：五条轨迹内随机留出的视觉 BC 指标和 checkpoint。
- `official_visual_baseline_holdout_159.json`、`official_visual_baseline_holdout_159.pt`：用 155–158 训练、159 独立验证的视觉 BC 结果。
- `official_five_file_014_audit.json`、`official_five_file_015_audit.json`：五条目标 episode 所在 Parquet 的完整数值审计。
- `official_temporal_samples_h4_c8.npz`：4 个历史时刻和 8 步动作块的五条演示缓存。
- `official_temporal_baseline_holdout_159.json`、对应 `.pt`：直接动作时序模型结果。
- `official_temporal_residual_baseline_holdout_159.json`、对应 `.pt`：分字段等权的残差时序模型结果。
- `official_temporal_hybrid_baseline_holdout_159.json`、对应 `.pt`：末端直接、夹爪和关节残差的混合目标对照。
- `*.log`：Isaac Sim / env server 日志。

这些文件可能很大，或含内部数据路径和元数据，因此不会同步到 GitHub。
