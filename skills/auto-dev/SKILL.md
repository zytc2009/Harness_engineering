---
name: auto-dev
description: C++ 自动化闭环开发。当用户说 "/auto-dev <需求文档>"、"自动开发"、"闭环开发"、"自动实现这个需求" 时触发。读取需求文档，拆解为原子任务，按依赖图事件驱动调度（依赖满足即启动，无需等待同层其他任务），每个任务走 实现→测试→lint→审查 闭环，测试失败自动修复（每任务最多 3 轮）。
---

# auto-dev — C++ 闭环自动开发

> **auto-dev 是编排器，harness-cpp 是约束系统。**
> auto-dev 负责 WHAT（任务调度），harness-cpp 负责 HOW（执行约束）。

---

## 触发方式

```
/auto-dev <需求文档路径>
/auto-dev docs/requirement.md

# 选项
/auto-dev --skip-design docs/req.md        # 已有设计文档，跳过 Phase 1
/auto-dev --platforms windows,macos docs/req.md  # 指定多平台
/auto-dev --test-only                       # 仅对已有代码跑测试+审查
/auto-dev --review-only                     # 仅审查
/auto-dev --resume                          # 从 TASK_STATE.md 恢复
/auto-dev --orchestrator opus --workers sonnet docs/req.md  # 模型路由
```

无参数时，提示用户提供需求文档路径。

---

## 前置条件

1. **harness-cpp 存在** — 检查 `harness-cpp/HARNESS.md`
2. **CMake 可用** — `cmake --version`
3. **需求文档存在** — 路径有效且非空

---

## 状态机

```
START → S0:INIT → S1:DESIGN → S2:DECOMPOSE → S3:CONFIRM
                                                  │ 确认
S_HALT ←── S4:SCHEDULE ←→ S5:WAIT ←→ S6:ON_COMPLETE
                                          │ 全部完成
                                    S7:INTEGRATE → S8:FINISH
```

| 阶段 | 做什么 | 加载协议 |
|------|--------|---------|
| S0: INIT | 创建 `.auto-dev/` 目录、读需求和 harness、创建 TASK_STATE.md | — |
| S1: DESIGN | 启动 architect agent → 输出设计文档 | — |
| S2: DECOMPOSE | 拆解原子任务 + 依赖图 | — |
| S3: CONFIRM | 展示给用户确认 | — |
| S4-S6: 事件循环 | 依赖满足即启动，无 Batch 概念 | **读 `protocols/scheduler.md`** |
| S7: INTEGRATE | 全量构建 + 测试 + **独立 evaluator 审查** + lint | — |
| S8: FINISH | 报告 + LESSONS_LEARNED + 清理 | — |

**核心：调度器按需加载协议文件，不一次性注入全部指令。**

---

## 各阶段要点

### S0-S3：初始化到确认

- **S0**: 创建 `.auto-dev/{reports,state,logs}/`，TASK_STATE.md 存 `.auto-dev/state/`
- **S1**: architect agent 读 `harness-cpp/roles/architect.md`，输出设计文档到 `docs/design/`
- **S2**: 原子任务标准 — 可独立编译测试、< 500 行、无文件重叠、声明 depends_on + blocks
- **S3**: 展示依赖图，**必须**用户确认后才执行

### S4-S6：事件循环

**读 `protocols/scheduler.md` 获取完整调度规则。**

核心行为：扫描依赖图 → 启动所有 ready 任务 → 等待任意完成 → 更新状态 → 循环。

### S4-S6 中启动 sub-agent 时

**读 `protocols/task-agent.md` 获取 prompt 模板和闭环控制规则。**

每个 sub-agent 内部闭环：实现 → 测试 → lint（`harness-cpp/linters/checks.md`）→ 审查。

### S7：集成验证

1. `cmake --build` 全量构建
2. `ctest` 全量测试
3. 运行 `harness-cpp/linters/checks.md` 全量 lint 检查
4. 启动**独立 evaluator agent**（读 `harness-cpp/roles/evaluator.md`），不是让实现者自审
5. 失败 → 归因 → 回退到事件循环（读 `protocols/recovery.md`）

### S8：收尾

1. 生成完成报告 → `.auto-dev/reports/AUTO_DEV_COMPLETION_REPORT.md`
2. 生成 LESSONS_LEARNED → `.auto-dev/reports/LESSONS_LEARNED.md`
3. 删除 TASK_STATE.md
4. 提示用户 git commit

---

## 断点恢复

检测到已有 `.auto-dev/state/TASK_STATE.md` 时，**读 `protocols/recovery.md`** 获取恢复策略。

---

## 重要约束

### 角色边界

| 角色 | 能做 | 不能做 |
|---|---|---|
| 调度器 | 状态机、依赖图、启动/监听 agent | 写代码、测试、审查 |
| 架构师 | 设计、接口、拆解 | 写实现 |
| 实现者 | 写代码、修 Bug | 改接口、改 scope 外文件 |
| 测试工程师 | 写测试、报告 | 修 Bug |
| 审查员 | 标注问题 | 修代码 |
| 评估者 | 独立验证、打分 | 修代码、改设计 |

### Harness 集成

- 角色读取 `harness-cpp/roles/<角色>.md`
- 实现遵循 `harness-cpp/TASK_PROTOCOL.md`
- 路径符合 `harness-cpp/IO_MAP.md`
- 代码满足 `harness-cpp/HARNESS.md` 不变量
- lint 检查使用 `harness-cpp/linters/checks.md`
- 审查过 `harness-cpp/REVIEW.md`

### 完成报告格式

```markdown
## auto-dev 完成报告

### 需求
<一句话>

### 任务执行摘要
| 任务 | 状态 | 重试 | 产出文件 |
|------|------|------|---------|

### 并发效率
- 任务总数 / 最大并发 / 总重试

### Evaluator 评估
<独立评估结果摘要>
```

### LESSONS_LEARNED 格式

```markdown
## 经验教训

### 重试原因分析
| 任务 | 重试次数 | 根因 | 建议新增的约束 |
|------|---------|------|---------------|

### 模式错误
<反复出现的问题模式，建议编码为 lint 规则>

### 改进建议
<对 harness 约束或 auto-dev 流程的改进建议>
```

---

## 目录结构

```
.auto-dev/
├── reports/          ← 任务和项目报告
├── state/            ← TASK_STATE.md（持久化）
└── logs/             ← 构建和测试日志
```

## 协议文件索引

| 文件 | 何时加载 | 内容 |
|------|---------|------|
| `protocols/scheduler.md` | S4-S6 事件循环 | 调度规则、并发安全、context budget |
| `protocols/task-agent.md` | 启动 sub-agent | prompt 模板、闭环控制、模型路由 |
| `protocols/recovery.md` | 断点恢复、故障处理 | 恢复策略、故障表、S_HALT 格式 |
