# 任务 Agent 协议

> 每个 sub-agent 的 prompt 结构、闭环控制和通信协议。
> 由调度器在启动 sub-agent 时按需加载。

---

## Prompt 模板

```
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
6. 运行 harness-cpp/linters/checks.md 中的自动化检查
   - 按检查项的修复指令自行修正
7. 将结果写入 TASK_STATE.md 对应任务区段：
   - 状态：completed / failed
   - 产出文件列表
   - 测试结果
   - 审查结果
   - lint 检查结果
   - 最终重试次数
```

---

## 闭环控制

### 重试机制

- 每任务独立 3 轮重试
- 每轮**只修上一轮的错误**，不做额外改动
- 错误必须结构化：`文件:行号 — 描述`

### 闭环流程

```
IMPLEMENT → TEST → LINT → REVIEW
    ↑                        │
    └── 失败 且 retries < 3 ─┘
```

### 复杂任务的逐步模式

对于 scope > 3 个文件或涉及平台层的任务，调度器可以选择逐步调度：为该任务的每个步骤单独启动 sub-agent，主控在中间做判断。

---

## 通信协议

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
  - 测试结果 + 审查结果 + lint 结果
  - 重试次数
```

---

## 模型路由

不同角色可使用不同模型以优化成本：

| 角色 | 默认模型 | 说明 |
|------|---------|------|
| 调度器（Orchestrator） | opus | 复杂决策、状态管理 |
| 架构师（Architect） | opus | 系统设计需要深度推理 |
| 实现者（Implementer） | sonnet | 代码生成，性价比最优 |
| 测试工程师（Test Engineer） | sonnet | 测试编写 |
| 审查员（Reviewer） | sonnet | 检查清单驱动 |
| 评估者（Evaluator） | sonnet | 独立验证 |

通过 `/auto-dev` 选项覆盖：

```
/auto-dev --orchestrator opus --workers sonnet docs/req.md
/auto-dev --all-opus docs/req.md       # 全部用 opus（贵但质量高）
/auto-dev --all-sonnet docs/req.md     # 全部用 sonnet（省钱）
```

Agent 启动时传入 model 参数：

```
Agent(description="T2: ...", prompt="...", model="sonnet", run_in_background=true)
```
