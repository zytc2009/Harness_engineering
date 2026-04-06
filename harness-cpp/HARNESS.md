# 智能体工作台（HARNESS）— 跨平台 C++20 项目
> 面向 Claude CLI 的 Harness Engineering 配置。
> 没有任何对话上下文的全新智能体，按顺序读完这几个文件后即可立刻开始工作。

---

## 阅读顺序

```
1. HARNESS.md          ← 你在这里。决策树 + 不变量 + 子系统地图。
2. BOOTSTRAP.md        ← 项目结构、CMake 命令、平台矩阵。
3. TASK_PROTOCOL.md    ← 任务拆解、C++ 实现顺序。
4. IO_MAP.md           ← 源码目录约定、构建产物路径、平台宏映射。
5. （执行工作）
6. linters/checks.md   ← 机械化检查（构建后、审查前）。
7. REVIEW.md           ← 完成前的检查清单（含 C++ 专属项）。
*  META.md             ← 版本、假设清单、边界声明（维护时读）。
*  roles/evaluator.md  ← 独立评估者角色（集成验证时读）。
```

---

## 角色系统

本 Harness 支持分角色工作。收到任务后，先确认你的角色，再进入决策树。

| 角色 | 文件 | 职责范围 |
|------|------|---------|
| 架构师 | `roles/architect.md` | 系统设计、模块划分、API 设计、依赖决策 |
| 实现者 | `roles/implementer.md` | 写代码、改 Bug、加功能 |
| 构建工程师 | `roles/build-engineer.md` | CMake、工具链、CI/CD、依赖管理 |
| 审查员 | `roles/reviewer.md` | 代码审查、安全审计、性能分析 |
| 测试工程师 | `roles/test-engineer.md` | 单元测试、集成测试、平台兼容性测试 |
| 移植工程师 | `roles/porter.md` | 平台适配、NDK 构建、平台特定 Bug |

**指定角色的方式**：在任务描述中声明，例如「以构建工程师角色修复 Android 链接错误」。
**未指定角色时**：默认为「实现者」。

---

## 决策树

```
收到任务 →

  确认角色（未指定 → 实现者）
    → 读对应的 roles/<角色>.md

  这是 Bug 修复？
    → 确定出问题的平台（Windows / macOS / Android）
    → 读 platforms/<平台>.md
    → 读 IO_MAP.md §「从哪里读」
    → 读 TASK_PROTOCOL.md §「阶段 A：理解」

  这是新功能？
    → 确定功能是否跨平台（影响几个平台？）
    → 完整执行 TASK_PROTOCOL.md（四个阶段全走）

  这是新增平台支持？
    → 读 platforms/<目标平台>.md
    → 读 roles/porter.md
    → 执行 TASK_PROTOCOL.md §「模式：平台适配」

  这是构建 / CMake 问题？
    → 读 roles/build-engineer.md
    → 读 BOOTSTRAP.md §「开发命令」
    → 读 IO_MAP.md §「CMake 模块注册」

  这是重构 / 清理？
    → 先读涉及的文件
    → 套用 TASK_PROTOCOL.md §「执行顺序规则」

  这是代码审查 / 审计？
    → 读 roles/reviewer.md
    → 直接跳到 REVIEW.md

  不确定？
    → 读下方「子系统地图」，确认任务归属，再重新从这里开始。
```

---

## 不变量 — 本项目永远成立的规则

```
C++ 标准：     C++20，所有平台统一。CMAKE_CXX_STANDARD 20，不允许降级。
内存管理：     RAII 强制。裸 new/delete 禁止出现在业务代码中。
               使用 std::unique_ptr 表示所有权，std::shared_ptr 仅用于真正的共享场景。
               原始指针仅用于非拥有引用（观察者模式），且生命周期必须由拥有者保证。
不可变性：     值对象一经构造不可修改（成员用 const 或提供 immutable 接口）。
               需要变更时创建新对象，不修改原对象。
平台隔离：     平台特定代码只允许出现在 src/platform/ 目录下。
               业务代码通过抽象接口访问平台能力，禁止 #ifdef 散落在业务逻辑中。
符号导出：     库的公共 API 必须通过 export macro 显式导出。
               内部符号默认隐藏（-fvisibility=hidden / MSVC 不导出即隐藏）。
错误处理：     使用 std::expected<T, Error>（C++23 polyfill）或项目 Result<T, E> 类型。
               禁止用异常做控制流。异常仅用于真正的异常情况，且不跨模块边界传播。
线程安全：     共享可变状态必须用 std::mutex 或 std::atomic 保护。
               优先使用消息传递（队列）而非共享内存。
编码规范：     文件名 snake_case，类名 PascalCase，函数/变量 snake_case，
               常量 kPascalCase，宏 ALL_CAPS。
               头文件用 #pragma once。
```

---

## 子系统地图

| 子系统 | 入口文件 | 备注 |
|--------|---------|------|
| 核心库 | `src/core/` | 平台无关的核心业务逻辑 |
| 平台抽象层 | `src/platform/` | 每个平台一个子目录，实现统一接口 |
| 公共 API | `include/` | 对外暴露的头文件，库的公共接口 |
| 应用层 | `app/` | 可执行程序入口，依赖核心库 |
| 第三方集成 | `third_party/` | 非 vcpkg 管理的第三方代码（尽量少） |
| 测试 | `tests/` | Google Test，镜像 src/ 的目录结构 |
| 工具 / 脚本 | `tools/` | 构建辅助脚本、代码生成器 |
| CMake 模块 | `cmake/` | 自定义 CMake 模块、工具链文件、Find 脚本 |

---

## 关键类型 / 接口（速查）

```cpp
// 平台抽象接口示例 — 所有平台特定实现必须继承此接口
class IPlatform {
    virtual auto get_name() const -> std::string_view = 0;
    virtual auto get_app_data_path() const -> std::filesystem::path = 0;
    virtual auto get_temp_path() const -> std::filesystem::path = 0;
    virtual ~IPlatform() = default;
};

// 错误处理类型
enum class ErrorCode { Ok, NotFound, PermissionDenied, IoError, InvalidArgument, ... };

struct Error {
    ErrorCode code;
    std::string message;
    std::source_location location;  // C++20: 自动捕获出错位置
};

template<typename T>
using Result = std::expected<T, Error>;  // 或项目自定义的 Result 类型

// 导出宏
#if defined(_WIN32)
  #define MY_API __declspec(dllexport)
#else
  #define MY_API __attribute__((visibility("default")))
#endif

// 模块注册（如果项目使用插件系统）
struct ModuleDescriptor {
    std::string_view name;
    std::string_view version;
    std::function<std::unique_ptr<IModule>()> factory;
};
```
