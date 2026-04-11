# Deprecated

此文件不再作为 `auto-dev` 的运行态状态模板。

原因：

- 执行状态由 `harness-runtime` 统一维护
- `task_queue.json` 是任务生命周期真相源
- `status.json` 是 worker 快照
- `auto-dev` 不应维护独立的 `进行中 / 待完成 / 重试计数 / 错误历史`

如需查询状态，请读取 runtime 的机器可读输出：

```bash
python harness-runtime/main.py --status-json
python harness-runtime/main.py --queue-json
```

如需提交任务，请使用规范任务文档并入队：

```bash
python harness-runtime/main.py --add-file <task-doc-path>
```

任务文档模板见：

- `docs/tasks/task-template.md`
