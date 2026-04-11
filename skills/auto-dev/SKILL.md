---
name: auto-dev
description: 通用需求澄清与任务入队 skill。用于和用户沟通需求、补齐约束、生成规范任务文档，并委托给 harness-runtime 批量执行。
---

# auto-dev

> `auto-dev` 是入口 skill，不是执行引擎。
> 它负责把模糊需求整理成可执行任务，然后交给 `harness-runtime`。

## 角色定位

`auto-dev` 只有两个职责：

1. 和用户沟通需求
2. 生成任务文档并入队

`auto-dev` 不负责：

- 自己执行实现
- 自己维护运行状态
- 自己承担完整调度循环

执行、重试、状态推进、队列管理，统一由 `harness-runtime` 负责。

当前边界设计见：

- `docs/superpowers/plans/2026-04-11-skill-runtime-boundary.md`

## 适用场景

当用户存在以下意图时使用本 skill：

- 想把一个需求整理成规范任务
- 需求还不够清楚，需要继续澄清
- 希望把整理好的任务提交给 runtime 执行

## 工作方式

### Step 1: 澄清需求

先判断用户描述是否已经足够清晰。

只有当下面信息足够明确时，才能进入任务文档生成阶段：

- `Goal`
- `Scope`
- `Inputs`
- `Outputs`
- `Acceptance Criteria`
- `Constraints`

如果缺失或模糊，主动追问。

追问原则：

- 只问缺的信息
- 优先问会影响执行边界的问题
- 不提前深入实现细节，除非用户明确要求

### Step 2: 生成规范任务文档

需求清晰后，生成 markdown 任务文档。

最小结构：

```md
# Task

## Goal
...

## Scope
- In scope: ...
- Out of scope: ...

## Inputs
- ...

## Outputs
- ...

## Acceptance Criteria
- ...
- ...

## Constraints
- language: ...
- platform: ...
- harness: ...
- dependency_policy: ...
- forbidden_paths: ...

## Status
ready
```

说明：

- `Constraints` 可以为空，但如果语言、平台、依赖限制、禁止修改路径等是关键约束，必须写清楚
- `Status` 必须为 `ready`
- 任务文档目标是让 runtime 无需再猜“到底要做什么”

### Step 3: 入队

任务文档准备完成后，委托给 `harness-runtime`：

```bash
python harness-runtime/main.py --add-file <task-doc-path>
```

## 语言策略

`auto-dev` 是 language-agnostic skill。

规则：

- 用户明确指定语言：写入 `Constraints`
- 用户没有指定语言但语言会影响执行：追问
- 用户没有指定语言且暂时不影响任务定义：可不填

`harness-cpp` 只是当前已经落地的一个 harness 示例，不是 `auto-dev` 的永久前置依赖。

长期模型是：

- `auto-dev`：语言无关的任务入口
- harness：语言或技术栈特化约束
- runtime：按任务元数据选择对应执行约束

## 状态边界

`auto-dev` 可以知道：

- 当前是否已经整理出任务文档
- 任务文档路径
- 入队是否成功
- 如需查询进度，应读取 runtime 的机器可读状态输出

`auto-dev` 不维护：

- `running`
- `failed`
- `retry_count`
- `phase`
- `duration_s`

这些状态由 runtime 维护。

## 与 runtime 的关系

`auto-dev` 和 `harness-runtime` 的职责分工：

- `auto-dev`：需求澄清、任务成型、入队
- `harness-runtime`：校验、排队、执行、重试、状态记录

一旦任务已经入队，执行态真相源只能是 runtime。

如果后续需要进度查询，应读取 runtime 状态，而不是在 skill 内维护另一套状态。

推荐读取方式：

```bash
python harness-runtime/main.py --status-json
python harness-runtime/main.py --queue-json
```

规则：

- 优先使用 JSON 输出给上层自动化消费
- 不要解析面向人类的终端格式输出作为状态真相源
- 如果需要回答“当前在做什么”或“队列里还有什么”，先读 runtime JSON 再总结给用户

## 输出要求

当你使用本 skill 时：

1. 如果需求不清晰，先提出必要问题
2. 如果需求足够清晰，整理成规范任务文档
3. 明确告知用户将通过 `--add-file` 入队
4. 如需查询执行进度，使用 `--status-json` / `--queue-json`
5. 不把自己描述成执行闭环调度器

## 禁止事项

不要在本 skill 中：

- 假装自己已经执行了任务
- 生成运行态状态机设计并把自己当成 worker
- 维护独立于 runtime 的任务生命周期记录
- 依赖手工维护的 markdown 状态模板作为运行态真相源
- 把 C++ harness 约束硬编码成 skill 的固定流程
