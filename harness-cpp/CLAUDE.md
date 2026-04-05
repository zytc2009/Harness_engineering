# Claude CLI 入口指引

> 全新智能体请先读 `harness-cpp/HARNESS.md`。

---

## 快速开始

本项目使用 **Harness Engineering** 配置管理智能体工作流。

### 阅读顺序
```
harness-cpp/HARNESS.md → BOOTSTRAP.md → TASK_PROTOCOL.md → IO_MAP.md → （执行） → REVIEW.md
```

### 角色指定

在任务描述中声明角色：
- `以架构师角色设计 xxx 模块的 API`
- `以实现者角色修复 xxx Bug`
- `以构建工程师角色添加 xxx 依赖`
- `以审查员角色审查最近的改动`
- `以测试工程师角色为 xxx 模块补充测试`
- `以移植工程师角色适配 Android 平台`

未指定角色时，默认为**实现者**。

### 平台信息

涉及特定平台时，读取对应说明：
- `harness-cpp/platforms/windows.md`
- `harness-cpp/platforms/macos.md`
- `harness-cpp/platforms/android.md`

---

## 项目概览

- **语言**：C++20
- **构建**：CMake + vcpkg
- **平台**：Windows / macOS / Android
- **测试**：Google Test
- **目标**：库 + 应用
