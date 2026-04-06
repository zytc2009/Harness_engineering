# Harness 元信息（META）

> 本文件记录 harness-cpp 的定位、版本、假设清单和边界声明。
> 模型升级或流程变更时，应重新审视此文件。

---

## 定位

```
Agent = Model + Harness

Harness（harness-cpp）= 约束系统
  → 不变量、角色、协议、检查清单、lint 规则
  → 负责 HOW：如何正确地执行任务

Skill（auto-dev）= 编排器
  → 状态机、依赖图、事件循环、sub-agent 调度
  → 负责 WHAT：调度哪些任务、何时启动

两者关系：auto-dev 调度任务，harness-cpp 约束执行。
未来可扩展：auto-dev 可对接其他 harness（如 harness-python、harness-rust）。
```

---

## 版本

| 字段 | 值 |
|------|---|
| Harness 版本 | 1.1.0 |
| 上次审视日期 | 2026-04-06 |
| 目标模型 | Claude Opus 4.6 / Sonnet 4.6 |
| C++ 标准 | C++20 |
| 目标平台 | Windows / macOS / Android |

---

## 假设清单

每个约束都编码了一个假设（"模型不能独立做 X"）。模型升级后应逐条压测，去掉不再承重的约束。

| # | 约束 | 假设 | 上次验证 | 状态 |
|---|------|------|---------|------|
| A1 | TASK_PROTOCOL 四阶段顺序执行 | agent 跳过理解/计划阶段会产生低质量代码 | 2026-04 | 保留 |
| A2 | 每任务 3 轮重试上限 | 超过 3 轮修复质量下降，陷入循环 | 2026-04 | 保留 |
| A3 | 头文件先于实现文件 | agent 不按此顺序时容易遗漏影响范围 | 2026-04 | 保留 |
| A4 | CMakeLists.txt 最后改 | agent 提前注册未完成的源文件导致构建失败 | 2026-04 | 保留 |
| A5 | 并发任务 scope 不可重叠 | agent 缺乏文件级锁，并发写同一文件导致冲突 | 2026-04 | 保留 |
| A6 | 裸 new/delete 禁止 | agent 倾向于写 C 风格内存管理 | 2026-04 | 保留 |
| A7 | 平台代码隔离到 src/platform/ | agent 会在核心代码中散落 #ifdef | 2026-04 | 保留 |
| A8 | REVIEW.md 检查清单 | agent 自审时倾向跳过安全和 ABI 检查 | 2026-04 | 保留 |
| A9 | 独立 Evaluator 角色 | agent 评估自己的工作时过度称赞 | 2026-04 | 新增 |
| A10 | lint 门控（机械化执行） | 文档检查清单会被忽略，自动化规则不会 | 2026-04 | 新增 |

### 如何压测假设

```
1. 选择一个假设（如 A3）
2. 在测试项目中去掉该约束
3. 让 agent 完成 3 个任务
4. 对比有/无约束的代码质量
5. 质量无显著差异 → 标记为"可移除"
6. 质量下降 → 保留，更新验证日期
```

---

## 文件清单

| 文件 | 职责 | 加载时机 |
|------|------|---------|
| `HARNESS.md` | 决策树 + 不变量 + 子系统地图 | agent 启动时 |
| `BOOTSTRAP.md` | 项目结构、CMake 命令、平台矩阵 | agent 启动时 |
| `TASK_PROTOCOL.md` | 任务拆解、执行顺序 | 实现阶段 |
| `IO_MAP.md` | 源码目录约定、路径映射 | 实现阶段 |
| `REVIEW.md` | 审查检查清单 | 验证阶段 |
| `META.md` | 本文件：版本、假设、边界 | 维护时 |
| `roles/*.md` | 角色定义 | 按角色加载 |
| `platforms/*.md` | 平台特定说明 | 按平台加载 |
| `linters/checks.md` | 机械化检查规则 | 测试/审查阶段 |

---

## 品味传播路径

```
agent 犯错
  → LESSONS_LEARNED.md 记录
    → 人类审阅
      → 编码为 linters/checks.md 新规则
        → 永久自动生效
```

这是 harness 持续改进的正向循环。每次 auto-dev 运行后生成的 LESSONS_LEARNED 是改进 harness 的输入源。
