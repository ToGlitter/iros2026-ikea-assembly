# Runtime logs

本目录用于本地运行日志。原始日志默认被 `.gitignore` 排除；需要长期保留的结论应整理到 `docs/PROGRESS.md`，避免提交巨大或包含敏感信息的日志文件。

本地运行会产生：

- `hdf5_schema.json`：HDF5 schema、统计量和抽样值。
- `ikea_smoke_result.json`：smoke rollout 指标。
- `ikea_smoke_frames/`：smoke 起止相机帧。
- `live/`：实时查看器相机帧和状态。
- `*.log`：Isaac Sim / env server 日志。

这些文件可能很大，或含内部数据路径和元数据，因此不会同步到 GitHub。
