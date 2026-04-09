# Harness Engineering

一套让 AI 智能体「开箱即用」的工程基础设施实践，以及基于该实践构建的 **C++ 自动化闭环开发工作台**。

---

## 核心理念

**Harness Engineering** 的目标：让任何一个全新的 AI 智能体——哪怕没有任何历史对话上下文——接到任务后直接开始工作，而不需要你先花时间给它讲解项目。

核心机制来源于对 Claude Code 工程模式的提炼：

- 任务生命周期管理（pending → running → completed / failed）
- 工具系统（接口定义 + 注册 + 权限门控 + 并发标志）
- 不可变状态管理（functional update 模式）
- 追加写入的磁盘输出（断点续读）
- 钩子驱动的生命周期自动化

---

## 多 Agent 协作 + 自动闭环设计

整个系统是一个 **Self-Refining Agent Loop（自我修复循环）**，最少由三个角色组成：

| Agent | 职责 |
|-------|------|
| 系统设计 Agent（架构师） | 定义架构、模块边界、接口规范，输出开发约束 |
| 开发 Agent（工程师）     | 根据设计实现代码、修复缺陷，可自迭代 |
| 测试 Agent（QA）         | 执行测试、发现问题、反馈给开发 Agent |

调度流程：

```
需求文档
   ↓
系统设计 Agent
   ↓
开发 Agent
   ↓
测试 Agent
   ↓
失败 → 回到开发 Agent 修复 → 再测（最多 N 轮）
   ↓
通过 → 输出结果
```

---

## 项目结构

```
Harness_engineering/
├── Agent.md                   # 多 Agent 协作 + 自动闭环设计方案（理论文档）
├── harness-template/          # 通用 Harness 模板（语言无关）
│   ├── 使用说明.md
│   ├── HOW_TO_INSTALL.md
│   ├── HARNESS.md             # 智能体入口：决策树、不变量、子系统地图
│   ├── BOOTSTRAP.md           # 项目定向：是什么项目、目录结构、开发命令
│   ├── TASK_PROTOCOL.md       # 任务协议：四阶段拆解、执行顺序规则
│   ├── IO_MAP.md              # 输入输出地图：读哪里、写哪里、状态约定
│   └── REVIEW.md              # 审查清单
├── harness-cpp/               # C++20 跨平台项目专用 Harness
│   ├── CLAUDE.md              # Claude CLI 入口指引
│   ├── HARNESS.md             # C++ 专属决策树 + 角色系统 + 不变量
│   ├── BOOTSTRAP.md           # CMake 命令、平台矩阵
│   ├── TASK_PROTOCOL.md       # C++ 任务拆解 + 实现顺序
│   ├── IO_MAP.md              # 源码目录约定、构建产物路径、平台宏映射
│   ├── REVIEW.md              # 完成前检查清单（含 C++ 专属项）
│   ├── roles/                 # 角色专属指引
│   │   ├── architect.md       # 系统设计、模块划分、API 设计
│   │   ├── implementer.md     # 写代码、改 Bug、加功能
│   │   ├── build-engineer.md  # CMake、工具链、CI/CD
│   │   ├── reviewer.md        # 代码审查、安全审计
│   │   ├── test-engineer.md   # 单元/集成/兼容性测试
│   │   └── porter.md          # 平台适配、NDK 构建
│   └── platforms/             # 平台专属说明
│       ├── windows.md
│       ├── macos.md
│       └── android.md
├── harness-runtime/           # 可运行的多 Agent 一次性流水线引擎
│   ├── .env.example           # 多 Provider 配置模板
│   ├── config.py              # 多 Provider LLM 工厂
│   ├── guard.py               # 3 级安全守卫
│   ├── memory.py              # 跨会话长期记忆
│   ├── tools.py               # 6 个沙箱工具
│   ├── prompts.py             # 三角色系统提示（含 I/O Contract 规范）
│   ├── orchestrator.py        # 流水线调度 + 语言感知测试分发
│   ├── main.py                # CLI 入口（任务注册/续跑/状态查询）
│   ├── harness_tasks.json     # 任务状态持久化
│   └── tests/                 # 测试套件
├── skills/
│   └── auto-dev/              # Claude Code skill：C++ 自动化闭环开发
│       ├── SKILL.md
│       └── TASK_STATE_TEMPLATE.md
└── docs/
    └── superpowers/plans/     # 实现计划文档
```

---

## auto-dev Skill

基于 `harness-cpp` 构建的 Claude Code skill，输入需求文档，自动完成从设计到测试的完整开发闭环。

### 触发方式

```
/auto-dev <需求文档路径>
/auto-dev docs/requirement.md

# 选项
/auto-dev --skip-design docs/req.md     # 已有设计文档，跳过 Phase 1
/auto-dev --platforms windows,macos docs/req.md  # 指定多平台
/auto-dev --test-only                   # 仅对已有代码跑测试+审查
/auto-dev --review-only                 # 仅审查
```

### 执行阶段

| 阶段 | 内容 |
|------|------|
| S0 INIT     | 读需求、创建目录结构、初始化状态 |
| S1 DESIGN   | architect agent 生成设计文档 |
| S2 DECOMPOSE | 拆解为原子任务 + 构建依赖图 |
| S3 CONFIRM  | 展示依赖图，用户确认 |
| S4–S6 执行  | sub-agent 实现→测试→审查闭环（事件驱动调度） |
| S7 INTEGRATE | cmake 构建 + ctest |
| S8 FINISH   | 生成报告，整理 `.auto-dev/` 目录 |

调度策略：某任务的所有前置依赖完成 → 立即启动该任务，不等待同层其他无关任务。测试失败自动修复，每任务最多 3 轮。

### 前置条件

- `harness-cpp/HARNESS.md` 存在
- `cmake --version` 可用
- 需求文档路径有效且非空

---

## harness-cpp 角色系统

```
以架构师角色设计 xxx 模块的 API
以实现者角色修复 xxx Bug
以构建工程师角色添加 xxx 依赖
以审查员角色审查最近的改动
以测试工程师角色为 xxx 模块补充测试
以移植工程师角色适配 Android 平台
```

未指定角色时，默认为**实现者**。

---

## harness-cpp 核心约束（不变量）

```
C++ 标准：     C++20，所有平台统一
内存管理：     RAII 强制，裸 new/delete 禁止出现在业务代码中
不可变性：     值对象一经构造不可修改，需要变更时创建新对象
平台隔离：     平台特定代码只允许出现在 src/platform/
错误处理：     使用 std::expected<T, Error>，禁止用异常做控制流
线程安全：     共享可变状态必须用 std::mutex 或 std::atomic 保护
编码规范：     文件名 snake_case，类名 PascalCase，函数/变量 snake_case
```

---

## 安装通用模板到新项目

```bash
# 1. 复制模板
cp -r harness-template/ <你的项目>/harness/

# 2. 按顺序填写五个文件（见 harness-template/使用说明.md）

# 3. 删除安装说明
rm harness/HOW_TO_INSTALL.md

# 4. 在 AGENTS.md 或 CLAUDE.md 中加一行入口提示
echo "> 全新智能体请先读 \`harness/HARNESS.md\`。" >> AGENTS.md
```

最低可用版本：只填 `HARNESS.md` + `BOOTSTRAP.md`，覆盖 80% 的任务场景。

---

## harness-runtime

可运行的多 Agent 一次性流水线引擎。每个阶段向 LLM 发起一次调用，无工具循环，无 ReAct 模式。

### 特性

| 特性 | 说明 |
|------|------|
| 多 Provider | 10+ 供应商：Anthropic、OpenAI、DeepSeek、Kimi、Qwen、GLM、MiniMax、Xiaomi、Ollama、Custom |
| 多 Agent 闭环 | architect → implementer → tester 自动循环，失败自动修复（最多 N 轮） |
| I/O Contract | architect 强制在设计文档中定义 stdin/stdout 格式，消除 implementer/tester 歧义 |
| 语言感知 tester | 自动检测实现语言，按扩展名分发执行器（Python / bash / C++ g++ 编译） |
| 任务状态记录 | `harness_tasks.json` 持久化 phase、retry_count、duration_s、error，支持 `--list` 查询 |
| 思考进度显示 | LLM 推理期间显示进度点，避免用户误以为程序卡住 |
| 断点续跑 | `--resume <id>` 从 implementer 阶段继续未完成的任务 |
| 跨会话记忆 | 自动提炼会话要点，下次启动时注入上下文 |
| 沙箱隔离 | 所有文件操作限定在系统临时目录内 |
| 安全守卫 | 3 级分类：auto-approve / always-confirm / keyword-check |

### 快速开始

```bash
cd harness-runtime
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入 Provider 和 API Key

python main.py                        # 新任务
python main.py --list                 # 列出所有历史任务（含状态/耗时/重试数）
python main.py --resume <task-id>     # 续跑未完成的任务
python main.py --phase implementer    # 从指定阶段开始
```

### Provider 配置示例

```bash
# Anthropic（默认）
PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key
MAIN_MODEL=claude-sonnet-4-6

# DeepSeek
PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_key
MAIN_MODEL=deepseek-chat

# Ollama（本地模型）
PROVIDER=ollama
MAIN_MODEL=gemma4:26b-a4b-it-q4_K_M
OPENAI_COMPATIBLE_API_KEY=ollama

# 任意 OpenAI 兼容 API
PROVIDER=custom
OPENAI_COMPATIBLE_BASE_URL=https://your-api/v1
OPENAI_COMPATIBLE_API_KEY=your_key
```

### 多 Provider 并行（每个 Agent 用不同模型）

每个 Agent 阶段可独立配置 Provider、模型和 Key，未设置的项自动回退到全局配置：

| 变量 | 说明 |
|------|------|
| `{PHASE}_PROVIDER` | 该阶段的 Provider（如 `ARCHITECT_PROVIDER=anthropic`） |
| `{PHASE}_MODEL` | 该阶段的模型 ID |
| `{PHASE}_API_KEY` | 该阶段的 API Key |
| `{PHASE}_BASE_URL` | 该阶段的 base URL（可选，已内置常用 Provider） |
| `{PHASE}_USER_AGENT` | 自定义 User-Agent（见下方风险提示） |

`PHASE` 取值：`ARCHITECT` / `IMPLEMENTER` / `TESTER`

```bash
# 示例：架构师用 Claude 推理，工程师用 Kimi，测试员用 MiniMax
PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

ARCHITECT_PROVIDER=anthropic
ARCHITECT_MODEL=claude-opus-4-6

IMPLEMENTER_PROVIDER=kimi
IMPLEMENTER_MODEL=moonshot-v1-8k
IMPLEMENTER_API_KEY=sk-...

TESTER_PROVIDER=minimax
TESTER_MODEL=MiniMax-M2.7
TESTER_API_KEY=sk-...
```

> **User-Agent 伪装（高风险）**
>
> 部分 API（如 Kimi For Coding）限制只允许特定客户端调用。`{PHASE}_USER_AGENT` 可注入自定义 UA 绕过此限制。
> **推荐优先申请无限制的标准 API Key**，确实只有受限 Key 时可用此方式，但需知悉：
> - 可能违反服务商 ToS，账号存在封禁风险
> - 服务商可能随时加强校验导致失效
>
> ```bash
> IMPLEMENTER_USER_AGENT=claude-code/1.0
> ```

### 架构（7 层）

| 层 | 文件 | 职责 |
|---|---|---|
| Config | `config.py` | 读 `.env`，按 Provider 构建 LLM 实例 |
| Prompts | `prompts.py` | 三角色系统提示 + I/O Contract 规范 + 长期记忆注入 |
| Tools | `tools.py` | 6 个沙箱工具，路径穿越防护 |
| Guard | `guard.py` | 3 级安全分类 + 人工确认 |
| Orchestrator | `orchestrator.py` | 一次性流水线 + 语言感知测试分发 |
| Memory | `memory.py` | 跨会话持久化（`memory.json`） |
| CLI | `main.py` | 入口，任务注册/续跑/状态查询 |

---

## 延伸阅读

- `Agent.md` — 多 Agent 协作与自动闭环设计的完整方案分析
- `harness-template/使用说明.md` — 通用模板的填写规则与常见问题
- `harness-cpp/HARNESS.md` — C++20 项目专属决策树与不变量
- `skills/auto-dev/SKILL.md` — auto-dev skill 完整规格与验证状态
- `docs/superpowers/plans/` — 实现计划文档
