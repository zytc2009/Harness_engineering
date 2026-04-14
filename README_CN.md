# Harness Engineering

将任务澄清与运行时执行分离的 AI 辅助开发基础设施。

仓库分为三层：

- `skills/auto-dev` — 需求接收、设计编排、任务入队引导
- `harness-runtime` — 队列管理、校验、执行、重试、状态上报
- `harness-*` — 栈特定约束包（例如 `harness-cpp`）

---

## 快速上手

```bash
# 提交内联任务
python harness-runtime/main.py --add "[Goal] 实现命令行计算器 [Language] C++ [Input] 从 stdin 读取表达式 [Output] 结果输出到 stdout"

# 校验并提交任务文档
python harness-runtime/main.py --validate-task-doc docs/tasks/task-001.md
python harness-runtime/main.py --add-file docs/tasks/task-001.md

# 查看队列和工作状态
python harness-runtime/main.py --queue
python harness-runtime/main.py --status
```

---

## 任务文档

运行时支持两种任务输入格式。

### 内联任务

通过 `--add` 直接传入的短任务。需要提供足够的上下文：

```text
[Goal] 一句话描述目标
[Language] Python / C++ / Go / Shell / 其他
[Input] 程序或功能接收什么
[Output] 应该产出什么
[Constraints] 可选：限制、依赖、平台要求
[Examples] 可选：示例输入/输出
```

### Markdown 任务文档

通过 `--add-file` 传入的结构化文档。规范模板：`docs/tasks/task-template.md`。

最少必需章节：

```markdown
## Goal
<要构建的内容>

## Inputs
<程序或功能接收什么>

## Outputs
<产出什么>

## Acceptance Criteria
<如何判断完成>

## Status
ready
```

常用可选章节：`Scope`、`Constraints`、`Open Questions`。

`--add-file` 只接受 `Status: ready` 的文档。

入队前建议先用 `--validate-task-doc` 校验文档。

---

## 运行时命令

```bash
python harness-runtime/main.py --add "<任务描述>"
python harness-runtime/main.py --add-file docs/tasks/task-001.md
python harness-runtime/main.py --validate-task-doc docs/tasks/task-001.md
python harness-runtime/main.py --queue
python harness-runtime/main.py --queue-json
python harness-runtime/main.py --status
python harness-runtime/main.py --status-json
python harness-runtime/main.py --cancel <task-id>
python harness-runtime/main.py --skip <task-id>
python harness-runtime/main.py --list
python harness-runtime/main.py --resume <task-id>
python harness-runtime/main.py --drain
```

| 命令 | 用途 |
|---|---|
| `--add` | 提交内联任务描述 |
| `--add-file` | 校验并提交 Markdown 任务文档 |
| `--validate-task-doc` | 校验任务文档，不入队 |
| `--queue` / `--queue-json` | 查看当前队列（人读 / 机读） |
| `--status` / `--status-json` | 查看最新工作快照（人读 / 机读） |
| `--cancel` / `--skip` | 按 id 操作待执行任务 |
| `--list` | 查看所有状态的已保存任务 |
| `--resume` | 按 id 重启已保存任务 |
| `--drain` | 处理所有待执行任务后退出 |

脚本读取输出时使用 `--queue-json` 和 `--status-json`。

队列状态持久化在 `harness-runtime/task_queue.json`。
工作状态持久化在 `harness-runtime/status.json`。

---

## 执行后端

每个流水线阶段（`architect`、`implementer`、`tester`）独立解析执行后端。支持两种模式：

- `provider` — 通过 provider、model 和凭证配置调用 API
- `cli` — 通过命令模板调用本地可执行程序

**解析优先级**（先匹配先生效）：

1. 阶段专属任务约束
2. 全局任务约束
3. 阶段专属环境变量
4. 全局环境变量
5. 运行时默认值（`provider`）

### Provider 模式

```markdown
## Constraints
- execution_mode: provider
- provider: deepseek
- model: deepseek-chat
```

或通过环境变量：

```env
ARCHITECT_EXECUTION_MODE=provider
ARCHITECT_PROVIDER=deepseek
ARCHITECT_MODEL=deepseek-reasoner
```

### CLI 模式

```markdown
## Constraints
- execution_mode: cli
- cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
- cli_timeout: 240
```

或通过环境变量：

```env
EXECUTION_MODE=cli
CLI_COMMAND=codex exec -c approval_mode=full-auto -o {output_file} -
CLI_TIMEOUT=180
```

`cli_timeout` 默认值为 `180` 秒。

**支持的占位符：**

| 占位符 | 行为 |
|---|---|
| `{prompt_file}` | 运行时将提示词写入临时文件并替换为其路径 |
| `{prompt_content}` | 运行时将完整提示词内联替换 |
| `{output_file}` | 运行时分配临时输出文件并替换为其路径 |

如果命令中没有 `{prompt_file}` 也没有 `{prompt_content}`，提示词通过 stdin 传入。输出从 `{output_file}` 读取（如已配置），否则从 stdout 读取。

### 混合模式示例

```markdown
## Constraints
- architect_execution_mode: provider
- architect_provider: deepseek
- architect_model: deepseek-reasoner
- implementer_execution_mode: cli
- implementer_cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
- tester_execution_mode: cli
- tester_cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
```

---

## 输出与版本控制

流水线成功执行后，生成文件可自动交付到目标目录。

| 约束 | 行为 |
|---|---|
| `workspace_dir` | 拷贝文件并创建 git commit，目录无仓库时自动初始化 |
| `output_dir` | 拷贝文件，不执行任何 git 操作 |

两者同时设置时，`workspace_dir` 优先生效。路径相对于项目根目录解析。

### 每个任务提交一次

```markdown
## Constraints
- workspace_dir: ../my-project
```

运行时拷贝所有生成文件，并以 `feat: <任务描述>` 为消息创建 commit。

### 仅拷贝

```markdown
## Constraints
- output_dir: output/puzzle-game
```

### 新建本地仓库

目标目录不含 `.git` 时，运行时自动初始化仓库。之后可手动关联远端：

```bash
git remote add origin <url> && git push -u origin main
```

---

## 任务拆解

对于复杂任务，architect 阶段可能在 `design.md` 旁边输出 `subtasks.json`。存在该文件时，运行时对每个子任务独立执行 `architect → implementer → commit` 流程。

相关约束：

| 约束 | 行为 |
|---|---|
| `workspace_dir` | 子任务 commit 落点仓库 |
| `subtask_tester` | 每个子任务完成后运行测试阶段 |
| `subtask_tester_last_only` | 仅对最后一个子任务运行测试（覆盖 `subtask_tester`） |

每个子任务的 commit 消息格式：

```
[subtask 2/5] Implement calculation core

acceptance_criteria: Addition, subtraction, multiplication, division work correctly.
```

---

## Harness 选择

在任务文档中声明 harness，加载栈特定的执行约束：

```markdown
## Constraints
- harness: harness-cpp
```

可用 harness：

| 包名 | 技术栈 |
|---|---|
| `harness-cpp` | C++20、CMake、vcpkg、Windows / macOS / Android |

---

## 关键路径

| 路径 | 用途 |
|---|---|
| `skills/auto-dev/` | 需求接收与任务编排 skill |
| `harness-runtime/` | 队列、执行引擎、状态管理 |
| `harness-cpp/` | C++ harness 约束与角色定义 |
| `docs/tasks/` | 任务文档与模板 |
| `docs/superpowers/` | 设计方案与架构笔记 |

---

## 参考文档

- 任务文档格式：`harness-runtime/TASK_FORMAT.md`
- C++ harness 不变量与角色系统：`harness-cpp/HARNESS.md`
- Harness 契约：`docs/superpowers/harness-contract.md`
- 任务模板：`docs/tasks/task-template.md`
