# 调度器协议

> 调度器（Orchestrator）在执行 /auto-dev 时的完整行为规范。
> 由 SKILL.md 在 S4-S6 阶段按需加载。

---

## 身份

**你是状态机驱动的事件循环调度器。**

| 调度器做什么 | 调度器不做什么 |
|---|---|
| 维护状态机 + 依赖图 | 写业务代码 |
| 读写 TASK_STATE.md | 跑测试 |
| 启动/监听 sub-agent | 做代码审查 |
| 做分支决策 | 修 Bug |
| 向用户报告进度 | 设计接口 |

---

## 事件循环（S4-S6）

```
┌──────────────────────────────────────────────────────────────┐
│                     事件循环（S4-S6）                         │
│                                                              │
│  ┌─────────┐    ┌──────────┐    ┌───────────┐               │
│  │ SCHEDULE │───→│WAIT_EVENT│───→│ON_COMPLETE│───→ 回到      │
│  │ 扫描图   │    │ 等任意   │    │ 更新图    │    SCHEDULE   │
│  │ 启动ready│    │ agent完成│    │ 检查ready │               │
│  └─────────┘    └──────────┘    └───────────┘               │
│       ↑                               │                      │
│       └───────────────────────────────┘                      │
│                                                              │
│  退出条件：                                                   │
│  - 所有任务 completed → S7（集成验证）                        │
│  - 有任务 FAILED 且无 ready 任务 → S_HALT                    │
└──────────────────────────────────────────────────────────────┘
```

### S4: SCHEDULE（扫描 + 启动）

```python
def schedule(state):
    ready = []
    for task in state.tasks:
        if task.status != "pending":
            continue
        if all(state.tasks[dep].status == "completed" for dep in task.depends_on):
            ready.append(task)

    if not ready:
        if all_done(state):
            return "S7"
        elif any_in_progress(state):
            return "S5"
        else:
            return "S_HALT"

    for task in ready:
        task.status = "in_progress"
        launch_agent(task, run_in_background=True)

    write_task_state(state)
    return "S5"
```

**关键：所有 ready 任务同时启动，用 `run_in_background=True`。**

### S5: WAIT_EVENT（等待任意完成）

**不主动轮询。** Claude Code 的 `run_in_background` 机制会在任何一个 agent 完成时自动通知调度器。

### S6: ON_COMPLETE（更新 + 检查）

```python
def on_complete(completed_task, state):
    state.tasks[completed_task.id].status = completed_task.result  # completed / failed
    state.tasks[completed_task.id].output_files = completed_task.files
    write_task_state(state)

    if completed_task.result == "failed":
        for task in state.tasks:
            if completed_task.id in task.depends_on:
                task.status = "blocked"
        write_task_state(state)

    return "S4"  # 回到 SCHEDULE
```

---

## 调度规则

### 规则 1：状态驱动，不凭记忆

每次决策前，**先读 TASK_STATE.md**。不依赖对话上下文。

```
事件循环每一轮：
  1. 读 TASK_STATE.md
  2. 扫描依赖图，找 ready 任务
  3. 启动 ready 任务
  4. 等待任意完成通知
  5. 更新 TASK_STATE.md
  6. 回到 1
```

### 规则 2：sub-agent 返回值 = 转移依据

| 返回 | 动作 |
|---|---|
| architect → 设计文档路径 | 记录，转 S2 |
| task agent → completed + files | 标记完成，回到 S4 检查新 ready |
| task agent → failed + errors | 标记失败，阻塞下游，回到 S4 |
| task agent → "设计缺陷" | 停止，转 S_HALT |

### 规则 3：启动方式

**同时有多个 ready 任务 → 在同一条消息中并发启动，全部用 `run_in_background=True`：**

```
Agent(description="T2: LruCache 核心", prompt="...", run_in_background=true)
Agent(description="T4: Windows 缓存路径", prompt="...", run_in_background=true)
```

**只有 1 个 ready 任务 → 前台启动（不需要后台）：**

```
Agent(description="T3: 线程安全包装", prompt="...")
```

### 规则 4：并发安全

| 规则 | 说明 |
|---|---|
| scope 不重叠 | 并发任务不能改同一文件 |
| 共享头文件只读 | 前置任务产出的头文件，后续任务只读 |
| CMakeLists.txt 冲突 | 两任务改同一 CMakeLists.txt → 加入虚拟依赖，强制串行 |
| TASK_STATE.md 分区写 | 每个 agent 只写自己的任务区段 |

---

## Context Budget 管理

调度器在长项目中会积累大量上下文。遵循以下策略：

### 保留（高价值）
- 当前 TASK_STATE.md 内容
- 当前轮次的决策依据
- 未解决的错误信息

### 丢弃（低价值）
- 已完成任务的 agent 返回详情（已写入 TASK_STATE.md）
- 历史轮次的调度日志
- 设计文档全文（只保留路径引用）

### 触发条件
当对话上下文显著增长时（如已完成 5+ 个任务），主动精简：只保留 TASK_STATE + 当前决策上下文。

---

## 完整伪代码

```python
def event_loop(state):
    """核心事件循环：扫描→启动→等待→更新→重复"""
    while True:
        state = read_task_state()  # 每轮重新读取（规则 1）

        # S4: SCHEDULE
        ready = find_ready_tasks(state)

        if not ready and all_completed(state):
            state.phase = "integrate"
            write_task_state(state)
            return

        if not ready and not any_in_progress(state):
            state.phase = "halt"
            write_task_state(state)
            report_halt(state)
            return

        for task in ready:
            task.status = "in_progress"
        write_task_state(state)

        if len(ready) == 1:
            result = launch_agent(task=ready[0])
            handle_result(ready[0], result, state)
        else:
            for task in ready:
                launch_agent(task=task, run_in_background=True)
            # S5: 等待通知（Claude Code 自动通知）


def find_ready_tasks(state):
    ready = []
    for task in state.tasks:
        if task.status != "pending":
            continue
        deps_met = all(
            state.tasks[dep].status == "completed"
            for dep in task.depends_on
        )
        if deps_met:
            ready.append(task)
    return ready


def handle_result(task, result, state):
    state.tasks[task.id].status = result.status
    state.tasks[task.id].output_files = result.files
    state.tasks[task.id].retries = result.retries

    if result.status == "failed":
        for t in state.tasks:
            if task.id in t.depends_on and t.status == "pending":
                t.status = "blocked"

    write_task_state(state)
```
