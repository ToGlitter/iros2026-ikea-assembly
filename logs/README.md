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
- `official159_lightwheel_demo0_comparison.json`：官方 episode 159 与 Lightwheel demo_0 的单样本 schema、相机、时序和动作空间对照。
- `official159_lightwheel_comparison_frames/`：两种数据源首/中/末阶段的 RGB 对照图。
- `official_five_task_segments.json`：官方 episodes 155–159 的逐帧 task_index 连续区间和技能时长统计。
- `lightwheel_local_manifest.json`：本机 Lightwheel HDF5 文件的轻量 manifest；当前只覆盖本地已有文件。
- `lightwheel_remote_manifest.json`：Lightwheel 远程 `data/` 目录的文件数量、逻辑大小和 LFS OID 清单；只读元数据。
- `official_remote_episode_manifest.json`：官方远程 episode metadata Parquet 的分页清单；只读元数据。
- `official_all_episode_metadata.json`：官方全部 533 条 episode 的长度、索引连续性、任务词汇和文件引用审计。
- `official_remote_data_manifest.json`：官方 52 个 frame data Parquet 的远程清单和大小/OID 校验信息。
- `official_all_episode_manifest.json`：全部 533 条 episode 的本地数据与视频引用规划。
- `official_all_task_segments.json`：全部 6,276,443 帧的 task_index 连续区间和技能分布。
- `official_balanced_segments_1000.json`：八个技能各 1,000 个、按 episode/frame 顺序排列的 anchor sampler smoke manifest。
- `official_155_159_balanced_segments_160.json`：episodes 155–159 的八技能平衡视觉 baseline anchor manifest。
- `official_balanced_visual_baseline_holdout_159.json`、对应 `.pt`：平衡采样视觉 baseline 的训练结果（Docker 运行后生成）。
- `official_155_159_balanced_action_distribution.json`：平衡 anchor 与均匀抽样的官方 50D 动作/状态分布对照。
- `first_stage_experiment_selection.json`：第一阶段官方 32 条和 Lightwheel 16 个唯一 HDF5 的 train/validation/test 选择。
- `official_first_stage_32_manifest.json`：官方第一阶段 32 条 episode 的 Parquet/RGB 引用规划。
- `official_first_stage_32_visual.json`、对应 `.pt`/`.npz`：官方 32 条视觉 BC 的训练结果、模型和采样缓存。
- `lightwheel_first_stage_local_manifest.json`：16 个 Lightwheel HDF5 的 schema、demo、帧数和成功标记汇总。
- `lightwheel_first_stage_state_head.json`、对应 `.pt`：Lightwheel 79D state 到 23D action head 结果。
- `lightwheel_first_stage_visual_head.json`、对应 `.pt`：Lightwheel 三路 RGB + 79D proprioception 到 23D action head 结果。
- `*.log`：Isaac Sim / env server 日志。

这些文件可能很大，或含内部数据路径和元数据，因此不会同步到 GitHub。
