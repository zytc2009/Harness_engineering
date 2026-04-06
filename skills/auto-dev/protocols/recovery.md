# 断点恢复与故障处理协议

> 会话中断后的恢复策略和各类故障的处理方式。
> 由调度器在检测到已有 TASK_STATE.md 时按需加载。

---

## 断点恢复

会话中断后，读 TASK_STATE.md 恢复：

```
1. 读 TASK_STATE.md，获取所有任务状态
2. in_progress 的任务：
   - git diff 检查 scope 内是否有改动
   - 有改动 → 视为实现完成，从测试步骤恢复
   - 无改动 → 从实现步骤恢复
3. pending 且依赖满足 → 启动
4. completed → 跳过
5. blocked → 检查其依赖的 failed 任务是否被用户修复了
6. 进入事件循环
```

---

## 故障处理表

| 场景 | 处理 |
|---|---|
| 需求文档不存在 | 报错，提示用户提供路径 |
| harness-cpp 不存在 | 报错，提示用户安装 harness |
| CMake 不可用 | 报错，提示安装 CMake |
| 用户不满意拆解 | 调整后重新确认 |
| 并发 scope 冲突 | 加虚拟依赖，强制串行 |
| 单任务编译失败 | 回到 IMPLEMENT，重试计数 +1 |
| 单任务 3 轮耗尽 | FAILED，阻塞下游，回到 S4 检查 |
| 全部卡住 | S_HALT，输出阻塞图，等待用户介入 |
| 集成失败 | 归因到具体任务，回退到事件循环 |
| 设计缺陷 | 停止，建议回 Phase 1 重新设计 |
| lint 检查失败 | agent 按修复指令自行修正，计入重试 |

---

## 集成失败归因

S7 集成验证失败时，精准定位责任任务：

```python
def diagnose(state, build_errors):
    for error in build_errors:
        faulty_file = error.file
        for task in state.tasks:
            if faulty_file in task.scope:
                return task.id
    # 如果无法归因到单个任务 → 可能是接口不兼容
    return "design_issue"
```

归因后：
- 回退该任务状态为 `pending`
- 重新进入事件循环
- 如果归因为 `design_issue` → S_HALT

---

## S_HALT 输出格式

```markdown
## auto-dev 已暂停

### 阻塞状态
| 任务 | 状态 | 原因 |
|------|------|------|
| T2 | FAILED | 3 轮重试耗尽，最后错误：src/core/cache.cpp:42 容量为0未返回 Error |
| T3 | BLOCKED | 依赖 T2 |

### 建议操作
1. 手动修复 T2 的问题，然后重新运行 `/auto-dev --resume`
2. 或修改设计文档后运行 `/auto-dev --skip-design docs/req.md`

### 用户介入后
运行 `/auto-dev --resume` 恢复执行。调度器会重新扫描 TASK_STATE.md。
```
