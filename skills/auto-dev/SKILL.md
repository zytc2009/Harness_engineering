---
name: auto-dev
description: C++ 自动化闭环开发。当用户说 "/auto-dev <需求文档>"、"自动开发"、"闭环开发"、"自动实现这个需求" 时触发。读取需求文档，拆解为原子任务，按依赖图事件驱动调度（依赖满足即启动，无需等待同层其他任务），每个任务走 实现→测试→审查 闭环，测试失败自动修复（每任务最多 3 轮）。
---

# auto-dev — C++ 闭环自动开发

将需求文档作为输入，**拆解为原子任务 + 构建依赖图**，以事件驱动方式调度：
**某任务的所有前置依赖完成 → 立即启动该任务**，不等待同层其他无关任务。
每个任务内部走 实现→测试→审查 闭环，失败自动修复。

---

## 验证状态（Validation Status）

> 最后更新：2026-04-05

### ✅ 已验证（端到端跑通）

以 `test-requirement-simple-cache.md`（LRU 缓存库）为测试用例，完整走完一次：

| 阶段 | 内容 | 结果 |
|------|------|------|
| S0 INIT | 读需求、创建目录结构、初始化状态 | ✅ |
| S1 DESIGN | architect agent 生成设计文档 | ✅ |
| S2 DECOMPOSE | 拆解为 10 个原子任务 + 依赖图 | ✅ |
| S3 CONFIRM | 展示依赖图，用户确认 | ✅ |
| S4-S6 执行 | sub-agent 实现→测试→审查闭环 | ✅（批次调度）|
| S7 INTEGRATE | cmake 构建 + ctest，39 个测试全部通过 | ✅ |
| S8 FINISH | 生成报告，整理 .auto-dev/ 目录 | ✅ |
| 单任务重试 | 测试失败时自动修复并重跑 | ✅（实际触发过） |

### ⚠️ 待验证（已设计，未实测）

| 特性 | 说明 | 优先级 |
|------|------|--------|
| **事件驱动调度（S4-S6）** | 测试时用的是批次调度，升级为事件驱动后未重新跑完整用例 | 高 |
| **真并发 `run_in_background=True`** | 多任务并发启动未在实际用例中触发验证 | 高 |
| **断点恢复（规则 5）** | 会话中断后读 TASK_STATE.md 恢复，未测试过 | 中 |
| **S_HALT 阻塞处理** | 全部任务卡住时的 halt + 报告流程 | 低 |
| **S7 失败归因回退** | 集成构建失败时，精准定位到任务并重新进入事件循环 | 中 |

### 升级路线建议

1. **下一步**：用一个新需求跑完整 `/auto-dev`，验证事件驱动调度和并发执行
2. **实现 generate_manifest / generate_index 函数**（目前是 stub，S8 调用的是占位符）
3. **断点恢复**：在会话中途强制中断，重新执行 `/auto-dev` 验证恢复逻辑
4. **多平台并发**：加入 Windows + macOS 同时构建的任务，验证平台任务并发

---

## 触发方式

```
/auto-dev <需求文档路径>
/auto-dev docs/requirement.md

# 选项
/auto-dev --skip-design docs/requirement.md    # 已有设计文档，跳过 Phase 1
/auto-dev --platforms windows,macos docs/req.md # 指定多平台
/auto-dev --test-only                          # 仅对已有代码跑测试+审查
/auto-dev --review-only                        # 仅审查
```

无参数时，提示用户提供需求文档路径。

---

## 前置条件

1. **harness-cpp 存在** — 检查 `harness-cpp/HARNESS.md`
2. **CMake 可用** — `cmake --version`
3. **需求文档存在** — 路径有效且非空

---

## 调度器

### 身份

**当你执行 /auto-dev 时，你的身份切换为 Orchestrator（调度器）。**
你不再是通用助手。你是状态机驱动的事件循环调度器。

| 调度器做什么 | 调度器不做什么 |
|---|---|
| 维护状态机 + 依赖图 | 写业务代码 |
| 读写 TASK_STATE.md | 跑测试 |
| 启动/监听 sub-agent | 做代码审查 |
| 做分支决策 | 修 Bug |
| 向用户报告进度 | 设计接口 |

---

### 状态机

```
                        ┌──────────┐
                        │  START   │
                        └────┬─────┘
                             │
                             ▼
                   ┌──────────────────┐
                   │  S0: INIT        │  主控执行：读需求、读 harness、创建状态文件
                   └────────┬─────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │  S1: DESIGN      │  启动 architect agent → 设计文档
                   └────────┬─────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │  S2: DECOMPOSE   │  拆解任务 → 依赖图
                   └────────┬─────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │  S3: CONFIRM     │  展示给用户 → 等待确认
                   └────────┬─────────┘
                            │ 确认
                            ▼
                   ┌──────────────────┐
                   │  S4: SCHEDULE    │◄──────────────────────┐
                   │  扫描依赖图      │                       │
                   │  启动所有 ready  │                       │
                   └────────┬─────────┘                       │
                            │                                 │
                            ▼                                 │
                   ┌──────────────────┐                       │
                   │  S5: WAIT_EVENT  │  等待任意 agent 完成   │
                   │                  │  （不是等全部）        │
                   └────────┬─────────┘                       │
                            │ 收到某个任务完成通知             │
                            ▼                                 │
                   ┌──────────────────┐                       │
                   │  S6: ON_COMPLETE │                       │
                   │  更新依赖图      │                       │
                   │  检查新解锁任务  │───→ 有新 ready → S4 ──┘
                   │                  │
                   │  全部完成 → S7   │
                   │  有 FAILED → S_HALT
                   └────────┬─────────┘
                            │ 全部完成
                            ▼
                   ┌──────────────────┐
                   │  S7: INTEGRATE   │  全量构建 + 测试 + 集成审查
                   │  PASS → S8      │
                   │  FAIL → 归因 → S4
                   └────────┬─────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │  S8: FINISH      │  报告 + 清理 + 提示 commit
                   └──────────────────┘

                   ┌──────────────────┐
                   │  S_HALT          │  任务耗尽重试 / 全部阻塞
                   │  输出失败报告    │  等待用户介入
                   └──────────────────┘
```

**核心区别：没有 Batch 概念。** S4→S5→S6 是一个事件循环，每完成一个任务就检查是否有新任务被解锁。

---

### 事件循环详解

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

#### S4: SCHEDULE（扫描 + 启动）

```python
def schedule(state):
    ready = []
    for task in state.tasks:
        if task.status != "pending":
            continue
        # 所有前置依赖都已 completed？
        if all(state.tasks[dep].status == "completed" for dep in task.depends_on):
            ready.append(task)

    if not ready:
        # 没有可启动的任务
        if all_done(state):
            return "S7"        # 全部完成 → 集成验证
        elif any_in_progress(state):
            return "S5"        # 还有任务在跑，继续等
        else:
            return "S_HALT"    # 全卡住了

    # 启动所有 ready 任务
    for task in ready:
        task.status = "in_progress"
        launch_agent(task, run_in_background=True)

    write_task_state(state)
    return "S5"  # 进入等待
```

**关键：所有 ready 任务同时启动，用 `run_in_background=True`。**

#### S5: WAIT_EVENT（等待任意完成）

**不主动轮询。** Claude Code 的 `run_in_background` 机制会在任何一个 agent 完成时自动通知调度器。

调度器收到通知后进入 S6。

#### S6: ON_COMPLETE（更新 + 检查）

```python
def on_complete(completed_task, state):
    # 1. 更新状态
    state.tasks[completed_task.id].status = completed_task.result  # completed / failed
    state.tasks[completed_task.id].output_files = completed_task.files
    write_task_state(state)

    # 2. 如果失败
    if completed_task.result == "failed":
        # 标记所有依赖它的任务为 blocked
        for task in state.tasks:
            if completed_task.id in task.depends_on:
                task.status = "blocked"
        write_task_state(state)

    # 3. 回到 SCHEDULE，检查是否有新任务被解锁
    return "S4"
```

---

### 并发时间线示例

```
时间 →

T1（无依赖）  ████ done
                │
                ├──→ T2（← T1）  ████████████████ done
                │                              │
                │                              └──→ T3（← T2）  ████████ done
                │
                ├──→ T4（← T1）  ████████ done      ← 不用等 T2
                │
                └──→ T5（← T1）  ██████████ done     ← 不用等 T2

T4 完成时：调度器检查 → 没有新任务被解锁（T3 还在等 T2）→ 继续等
T2 完成时：调度器检查 → T3 的依赖满足了！→ 立即启动 T3
T5 完成时：调度器检查 → 没有新解锁 → 继续等
T3 完成时：调度器检查 → 全部完成 → 进入集成验证
```

**对比 Batch 调度：** T3 不再等 T4、T5。节省了 T4/T5 的空闲等待时间。

---

### 调度规则

#### 规则 1：状态驱动，不凭记忆

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

#### 规则 2：sub-agent 返回值 = 转移依据

| 返回 | 动作 |
|---|---|
| architect → 设计文档路径 | 记录，转 S2 |
| task agent → completed + files | 标记完成，回到 S4 检查新 ready |
| task agent → failed + errors | 标记失败，阻塞下游，回到 S4 |
| task agent → "设计缺陷" | 停止，转 S_HALT |

#### 规则 3：启动方式

**同时有多个 ready 任务 → 在同一条消息中并发启动，全部用 `run_in_background=True`：**

```
Agent(description="T2: LruCache 核心", prompt="...", run_in_background=true)
Agent(description="T4: Windows 缓存路径", prompt="...", run_in_background=true)
Agent(description="T5: macOS 缓存路径", prompt="...", run_in_background=true)
```

**只有 1 个 ready 任务 → 前台启动（不需要后台）：**

```
Agent(description="T3: 线程安全包装", prompt="...")
```

#### 规则 4：任务内部闭环

每个任务 agent 在内部完成 实现→测试→审查 循环：

```
prompt 结构：
  你负责完成任务 <task_id>: <task_name>。

  你的工作范围（scope）：<文件列表>
  只允许修改这些文件。可以读取前置任务产出的文件。

  设计文档：<path>
  当前重试次数：<N> / 3

  按以下顺序执行：
  1. 读取 harness-cpp/roles/implementer.md，以实现者角色编写代码
     - 遵循 harness-cpp/TASK_PROTOCOL.md 四阶段
     - 遵循 harness-cpp/IO_MAP.md 文件路径约定
     - 遵循 harness-cpp/HARNESS.md 不变量
  2. 读取 harness-cpp/roles/test-engineer.md，以测试工程师角色写测试
     - 运行 cmake --build + ctest
  3. 如果测试失败且重试 < 3：修复并重新测试
  4. 读取 harness-cpp/roles/reviewer.md，以审查员角色审查
     - 过 harness-cpp/REVIEW.md 检查清单
  5. 如果有 CRITICAL/HIGH 且重试 < 3：修复并重回步骤 2
  6. 将结果写入 TASK_STATE.md 对应任务区段：
     - 状态：completed / failed
     - 产出文件列表
     - 测试结果
     - 审查结果
     - 最终重试次数
```

对于复杂任务（scope > 3 个文件 或涉及平台层），调度器可以选择逐步调度模式：
为该任务的每个步骤单独启动 sub-agent，主控在中间做判断。

#### 规则 5：断点恢复

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

#### 规则 6：并发安全

| 规则 | 说明 |
|---|---|
| scope 不重叠 | 并发任务不能改同一文件 |
| 共享头文件只读 | 前置任务产出的头文件，后续任务只读 |
| CMakeLists.txt 冲突 | 两任务改同一 CMakeLists.txt → 加入虚拟依赖，强制串行 |
| TASK_STATE.md 分区写 | 每个 agent 只写自己的任务区段 |

---

### 通信协议

**唯一通信通道：TASK_STATE.md**

```
调度器 → sub-agent（通过 Agent prompt）：
  - 任务信息（id, name, scope, depends_on）
  - 角色 .md 文件路径
  - 设计文档路径
  - TASK_STATE.md 路径
  - 当前重试次数 + 上一轮错误列表

sub-agent → 调度器（写 TASK_STATE.md + Agent 返回值）：
  - 任务状态（completed / failed）
  - 产出文件列表
  - 测试结果 + 审查结果
  - 重试次数
```

---

### 完整伪代码

```python
def auto_dev(requirement_path):
    # ═══ S0: INIT ═══
    # 1. 创建 .auto-dev/ 目录结构用于管理生成的文件
    create_directory_structure()

    state = read_or_create_task_state()
    if state.phase == "not_started":
        requirement = read(requirement_path)
        harness = read_harness()
        state = create_task_state(requirement, harness)
        state.phase = "design"
        state.auto_dev_dir = ".auto-dev"  # 记录输出目录
        write_task_state(state)

    # ═══ S1: DESIGN ═══
    if state.phase == "design":
        result = launch_agent(role="architect", prompt=f"""
            读取 harness-cpp/roles/architect.md
            读取需求文档: {requirement_path}
            输出设计文档到 docs/design/
        """)
        state.design_doc = result.path
        state.phase = "decompose"
        write_task_state(state)

    # ═══ S2: DECOMPOSE ═══
    if state.phase == "decompose":
        tasks = decompose(state.design_doc)  # 拆解 + 依赖图
        state.tasks = tasks
        state.phase = "confirm"
        write_task_state(state)

    # ═══ S3: CONFIRM ═══
    if state.phase == "confirm":
        show_dependency_graph(state.tasks)
        # 暂停，等用户确认或调整
        state.phase = "executing"
        write_task_state(state)

    # ═══ S4-S6: 事件循环 ═══
    if state.phase == "executing":
        event_loop(state)

    # ═══ S7: INTEGRATE ═══
    if state.phase == "integrate":
        build_ok = run("cmake --build --preset <平台>-debug")
        test_ok  = run("ctest --preset <平台>-debug --output-on-failure")

        if not (build_ok and test_ok):
            faulty = diagnose(state)
            state.tasks[faulty].status = "pending"  # 回退
            state.tasks[faulty].retries += 0  # 不额外加，内部闭环会加
            state.phase = "executing"
            write_task_state(state)
            event_loop(state)  # 重新进入
            return

        review = launch_agent(role="reviewer", scope="integration")
        if review.has_critical:
            # 同上逻辑
            ...

        state.phase = "finish"
        write_task_state(state)

    # ═══ S8: FINISH ═══
    if state.phase == "finish":
        # 1. 生成完成报告
        report_path = generate_report(state)

        # 2. 整理文件结构
        organize_auto_dev_files(state.auto_dev_dir, report_path)

        # 3. 保存最终状态，然后删除
        state.phase = "completed"
        write_task_state(state)
        delete_task_state()

        # 4. 清理并提示用户
        ask_user_about_commit()


def event_loop(state):
    """核心事件循环：扫描→启动→等待→更新→重复"""
    while True:
        state = read_task_state()  # 每轮重新读取（规则 1）

        # ─── S4: SCHEDULE ───
        ready = find_ready_tasks(state)

        if not ready and all_completed(state):
            state.phase = "integrate"
            write_task_state(state)
            return  # 退出循环 → 集成验证

        if not ready and not any_in_progress(state):
            state.phase = "halt"
            write_task_state(state)
            report_halt(state)  # 全卡住了
            return

        # 启动所有 ready 任务
        for task in ready:
            task.status = "in_progress"
        write_task_state(state)

        if len(ready) == 1:
            # 单任务：前台执行
            result = launch_agent(task=ready[0])
            handle_result(ready[0], result, state)
        else:
            # 多任务：后台并发
            for task in ready:
                launch_agent(task=task, run_in_background=True)

            # ─── S5: WAIT_EVENT ───
            # 等待通知（Claude Code 自动通知，不轮询）
            # 收到通知后 handle_result
            ...

        # ─── S6: ON_COMPLETE ───
        # handle_result 更新状态后，回到循环顶部


def find_ready_tasks(state):
    """找出所有依赖已满足的 pending 任务"""
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
    """处理单个任务完成事件"""
    state.tasks[task.id].status = result.status
    state.tasks[task.id].output_files = result.files
    state.tasks[task.id].retries = result.retries

    if result.status == "failed":
        # 阻塞所有下游任务
        for t in state.tasks:
            if task.id in t.depends_on and t.status == "pending":
                t.status = "blocked"

    write_task_state(state)


def create_directory_structure(auto_dev_dir=".auto-dev"):
    """创建 .auto-dev 目录结构用于管理自动开发的产出物"""
    import os
    dirs = [
        f"{auto_dev_dir}/reports",      # 任务和项目报告
        f"{auto_dev_dir}/state",        # 任务状态文件（TASK_STATE.md）
        f"{auto_dev_dir}/logs"          # 构建和测试日志
    ]
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)


def organize_auto_dev_files(auto_dev_dir, report_path):
    """整理 .auto-dev 目录中的文件，生成索引和清单"""
    import os

    # 1. 生成清单文件（MANIFEST.md）
    manifest = generate_manifest(auto_dev_dir)
    write(f"{auto_dev_dir}/MANIFEST.md", manifest)

    # 2. 生成快速索引（INDEX.md）
    index = generate_index(auto_dev_dir, report_path)
    write(f"{auto_dev_dir}/INDEX.md", index)

    # 3. 生成 .gitignore（排除日志和临时文件）
    gitignore = f"""# auto-dev 临时文件
{auto_dev_dir}/logs/
*.output

# 构建产出
build/
cmake-build-*/
CMakeFiles/
CMakeCache.txt

# IDE
.idea/
.vs/
.vscode/
*.code-workspace

# OS
.DS_Store
Thumbs.db
*.tmp
"""
    write(".gitignore", gitignore)

    print(f"✓ 项目已整理到 {auto_dev_dir}/ 目录")
    print(f"  - 报告: {auto_dev_dir}/reports/")
    print(f"  - 状态: {auto_dev_dir}/state/")
    print(f"  - 日志: {auto_dev_dir}/logs/")


def generate_manifest(auto_dev_dir):
    """生成项目清单文档（含文件统计、任务记录）"""
    # 实现应读取所有产出文件，统计行数、测试数、覆盖率等
    # 返回格式化的 Markdown
    pass


def generate_index(auto_dev_dir, report_path):
    """生成快速索引文档（含快速导航、常用命令）"""
    # 实现应生成结构化的索引，包含：
    # - 项目概览
    # - 文件位置导航
    # - 关键统计指标
    # - 常用命令速查
    pass
```

---

## 执行流程

### Phase 0：初始化

1. **自动创建目录结构** — 生成 `.auto-dev/{reports,state,logs}/` 目录
   - 所有任务报告 → `.auto-dev/reports/`
   - 任务状态文件 → `.auto-dev/state/TASK_STATE.md`
   - 构建和测试日志 → `.auto-dev/logs/`

2. 读需求文档 → 提取目标、模块、验收标准、平台
3. 读 harness → HARNESS.md / BOOTSTRAP.md / IO_MAP.md
4. 创建 TASK_STATE.md（保存在 `.auto-dev/state/` 目录）

### Phase 1：架构设计

启动 architect agent → 输出 `docs/design/<功能名>_design.md`

内容：模块划分、接口定义、文件清单、平台分析、ABI 评估、**依赖拓扑**

### Phase 2：任务拆解

**原子任务标准：**
- 1 模块或 1 紧密文件组
- 可独立编译、测试
- < 500 行改动

**拆解维度：** 模块边界 > 平台层 > 接口/实现 > 功能点

**依赖图构建：** 每个任务声明 depends_on + blocks

**用户确认（必须）：** 展示依赖图，用户确认/调整后才开始

### Phase 3：任务执行（事件驱动）

进入 S4-S6 事件循环。无 Batch 概念，依赖满足即启动。

### Phase 4：集成验证

所有任务完成后：
1. `cmake --build` 全量构建
2. `ctest` 全量测试
3. 集成审查（跨模块交互）
4. 失败 → 归因 → 回退到事件循环

### Phase 5：收尾

输出完成报告 → 删除 TASK_STATE.md → 提示 git commit

**报告格式：**

```markdown
## auto-dev 完成报告

### 需求
<一句话>

### 任务执行摘要
| 任务 | 状态 | 重试 | 耗时排位 | 产出文件 |
|------|------|------|---------|---------|
| T1 | PASS | 0/3 | 1st done | include/proj/cache.h |
| T4 | PASS | 0/3 | 2nd done | src/platform/windows/ |
| T5 | PASS | 0/3 | 3rd done | src/platform/macos/ |
| T2 | PASS | 1/3 | 4th done | src/core/lru_cache.* |
| T3 | PASS | 0/3 | 5th done | src/core/thread_safe_cache.* |

### 并发效率
- 任务总数: 5
- 最大并发: 3（T2 + T4 + T5 同时运行）
- 总重试: 1
```

---

## 重要约束

### 任务拆解

- 原子性：可独立编译、测试、审查
- 无文件重叠：并发任务 scope 不含相同文件
- 依赖完备：B 读 A 的产出 → B depends_on A
- 粒度适中：< 500 行不拆，> 100 行才拆
- 用户确认：必须经确认才执行

### 闭环控制

- 每任务独立 3 轮重试
- 每轮只修上一轮错误
- 结构化错误：文件+行号+描述
- 集成失败精准归因

### 角色边界

| 角色 | 能做 | 不能做 |
|---|---|---|
| 调度器 | 状态机、依赖图、启动/监听 agent | 写代码、测试、审查 |
| 架构师 | 设计、接口、拆解 | 写实现 |
| 实现者 | 写代码、修 Bug | 改接口、改 scope 外文件 |
| 测试工程师 | 写测试、报告 | 修 Bug |
| 审查员 | 标注问题 | 修代码 |

### Harness 集成

- 角色读取 `roles/<角色>.md`
- 实现者遵循 `TASK_PROTOCOL.md`
- 审查员过 `REVIEW.md`
- 路径符合 `IO_MAP.md`
- 代码满足 `HARNESS.md` 不变量

### 目录管理

**S0 初始化自动创建的目录结构：**

```
.auto-dev/
├── reports/              ← 任务和项目报告（可归档）
│   ├── T1_COMPLETION_REPORT.md
│   ├── T2_COMPLETION_REPORT.md
│   ├── ...
│   ├── AUTO_DEV_COMPLETION_REPORT.md
│   └── PROJECT_FINAL_SUMMARY.md
│
├── state/                ← 任务状态（持久化，必保留）
│   └── TASK_STATE.md
│
└── logs/                 ← 构建和测试日志（可清理）
    └── (cmake/ctest 日志)
```

**规则：**
- 所有生成的报告文件 → `.auto-dev/reports/`
- TASK_STATE.md → `.auto-dev/state/TASK_STATE.md`
- 项目源代码保持不变（src/, include/, tests/, docs/, CMakeLists.txt）
- S8 完成时自动生成：
  - `.auto-dev/MANIFEST.md` — 详细清单（文件统计、任务记录、验收标准）
  - `.auto-dev/INDEX.md` — 快速索引（导航、常用命令、项目统计）
  - `.gitignore` — 排除临时文件和构建产出

---

## 故障处理

| 场景 | 处理 |
|---|---|
| 需求文档不存在 | 报错 |
| 用户不满意拆解 | 调整后重新确认 |
| 并发 scope 冲突 | 加虚拟依赖，强制串行 |
| 单任务编译失败 | 回到 IMPLEMENT |
| 单任务 3 轮耗尽 | FAILED，阻塞下游，回到 S4 检查 |
| 全部卡住 | S_HALT，输出阻塞图 |
| 集成失败 | 归因任务，回退到事件循环 |
| 设计缺陷 | 停止，建议回 Phase 1 |

---

## 状态文件

```markdown
## 任务目标
<一句话>

## 当前阶段
executing  (not_started|design|decompose|confirm|executing|integrate|finish|halt)

## 设计文档
docs/design/<功能名>_design.md

## 依赖图

### T1: 定义 ICache 接口
- 状态：completed
- scope：include/proj/cache.h
- depends_on：无
- blocks：T2, T4, T5
- 重试：0 / 3
- 产出：include/proj/cache.h
- 完成顺序：#1

### T2: LruCache 核心逻辑
- 状态：in_progress
- scope：src/core/lru_cache.h, src/core/lru_cache.cpp, tests/core/lru_cache_test.cpp
- depends_on：T1
- blocks：T3
- 重试：1 / 3
- 当前错误：
  - src/core/lru_cache.cpp:42 — 容量为0未返回 Error

### T3: 线程安全包装
- 状态：pending
- scope：src/core/thread_safe_cache.h, src/core/thread_safe_cache.cpp
- depends_on：T2
- blocks：无

### T4: Windows 缓存路径
- 状态：completed
- scope：src/platform/windows/cache_path.cpp
- depends_on：T1
- blocks：无
- 重试：0 / 3
- 产出：src/platform/windows/cache_path.cpp
- 完成顺序：#2

### T5: macOS 缓存路径
- 状态：completed
- scope：src/platform/macos/cache_path.cpp
- depends_on：T1
- blocks：无
- 重试：0 / 3
- 产出：src/platform/macos/cache_path.cpp
- 完成顺序：#3

## 运行中的 Agent
- T2: background agent (started: 14:32)

## 完成顺序
1. T1 (14:30)
2. T4 (14:33)
3. T5 (14:34)

## 集成验证
- 状态：pending
```

---

## 示例执行过程

```
用户: /auto-dev docs/feature-file-cache.md

[S0: INIT]
  读需求：LRU 文件缓存
  创建 TASK_STATE.md (phase: design)

[S1: DESIGN]
  architect agent → docs/design/file_cache_design.md

[S2: DECOMPOSE]
  拆解为 5 个任务：
    T1: ICache 接口（无依赖）
    T2: LruCache 核心（← T1）
    T3: 线程安全包装（← T2）
    T4: Windows 适配（← T1）
    T5: macOS 适配（← T1）

[S3: CONFIRM]
  展示依赖图：
    T1 ──→ T2 ──→ T3
     ├──→ T4
     └──→ T5
  用户确认 ✅

[S4: SCHEDULE] 扫描 → T1 ready
  启动 T1（前台，唯一一个）

[S6: ON_COMPLETE] T1 completed
  检查 → T2, T4, T5 的依赖满足了！

[S4: SCHEDULE] 扫描 → T2, T4, T5 ready
  并发启动 3 个 agent（后台）：
    Agent(T2, run_in_background=true)
    Agent(T4, run_in_background=true)
    Agent(T5, run_in_background=true)

[S5: WAIT_EVENT]

[S6: ON_COMPLETE] T4 completed (最快完成)
  检查 → 无新任务解锁

[S5: WAIT_EVENT]

[S6: ON_COMPLETE] T5 completed
  检查 → 无新任务解锁

[S5: WAIT_EVENT]

[S6: ON_COMPLETE] T2 completed (1次重试后通过)
  检查 → T3 的依赖 (T2) 满足了！

[S4: SCHEDULE] 扫描 → T3 ready
  启动 T3（前台，唯一一个）

[S6: ON_COMPLETE] T3 completed
  检查 → 全部完成

[S7: INTEGRATE]
  cmake --build: OK
  ctest: ALL PASSED (18 tests)
  集成审查: PASS

[S8: FINISH]
  报告：5 任务 | 最大并发 3 | 1 次重试
  提示：是否 git commit？
```
