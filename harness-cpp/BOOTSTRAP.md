# 项目引导（BOOTSTRAP）— 跨平台 C++20 项目
> 为全新智能体提供项目定向信息。

---

## 这是什么项目？

跨平台 C++20 项目，同时包含库（library）和应用（application）两种目标。
构建系统为 CMake，包管理用 vcpkg，目标平台覆盖 Windows、macOS、Android。
测试框架为 Google Test。

---

## 目录结构

```
项目根/
  CMakeLists.txt          顶层 CMake，定义项目和全局选项
  CMakePresets.json        预设配置（平台 × 构建类型）
  vcpkg.json               依赖清单
  include/                 公共头文件（库的对外 API）
    <项目名>/
      *.h
  src/
    core/                  平台无关的核心逻辑
      CMakeLists.txt
      *.cpp / *.h
    platform/              平台抽象层
      platform.h           统一接口定义
      windows/             Windows 实现
      macos/               macOS 实现
      android/             Android 实现（JNI 桥接）
      CMakeLists.txt
  app/                     可执行程序
    CMakeLists.txt
    main.cpp
  tests/                   测试（镜像 src/ 结构）
    CMakeLists.txt
    core/
      *_test.cpp
    platform/
      *_test.cpp
  cmake/                   自定义 CMake 模块
    toolchains/            工具链文件
      android.toolchain.cmake
    modules/               Find 模块、工具函数
  tools/                   辅助脚本
  third_party/             非 vcpkg 管理的第三方（尽量为空）
  harness/                 本 Harness 文件
  CLAUDE.md                Claude CLI 入口指引
```

---

## 入口文件

| 文件 | 职责 |
|------|------|
| `CMakeLists.txt` | 项目顶层配置，全局编译选项、子目录声明 |
| `CMakePresets.json` | 所有平台 × 构建类型的预设（configure + build + test） |
| `vcpkg.json` | 依赖声明 + 版本锁定 |
| `include/<项目名>/` | 库的公共 API 头文件 |
| `src/platform/platform.h` | 平台抽象层统一接口 |
| `src/core/` | 核心业务逻辑入口 |
| `app/main.cpp` | 应用程序入口 |
| `tests/CMakeLists.txt` | 测试目标注册 |

---

## 语言、风格与约定

- **语言 / 标准**：C++20，`CMAKE_CXX_STANDARD 20`，`CMAKE_CXX_STANDARD_REQUIRED ON`
- **编译器**：MSVC 19.30+（Windows）、Apple Clang 14+（macOS）、NDK r25+ Clang（Android）
- **命名规范**：
  - 文件名：`snake_case.h` / `snake_case.cpp`
  - 类 / 结构体：`PascalCase`
  - 函数 / 变量：`snake_case`
  - 常量：`kPascalCase`
  - 宏：`ALL_CAPS`，必须带项目前缀
  - 命名空间：`snake_case`，顶层用项目名
- **头文件保护**：`#pragma once`
- **include 顺序**（clang-format 强制）：
  1. 对应的头文件（`foo.cpp` → `foo.h`）
  2. 项目内头文件
  3. 第三方库头文件
  4. 标准库头文件
- **文件大小**：头文件 < 300 行，实现文件 < 500 行，最大 800 行
- **函数长度**：< 50 行
- **嵌套深度**：< 4 层

---

## 平台矩阵

| 平台 | 编译器 | 构建类型 | 特殊说明 |
|------|-------|---------|---------|
| Windows | MSVC 19.30+ | Debug / Release / RelWithDebInfo | 默认开发平台 |
| macOS | Apple Clang 14+ | Debug / Release | 需要 Xcode Command Line Tools |
| Android | NDK r25+ (Clang) | Debug / Release | 需要 Android SDK + NDK，最低 API 24 |

---

## 开发命令

```bash
# === 依赖安装 ===
vcpkg install                              # 安装 vcpkg.json 中声明的依赖

# === 配置（使用预设） ===
cmake --preset windows-debug               # Windows Debug
cmake --preset windows-release             # Windows Release
cmake --preset macos-debug                 # macOS Debug
cmake --preset macos-release               # macOS Release
cmake --preset android-debug               # Android Debug（需要 NDK）
cmake --preset android-release             # Android Release

# === 构建 ===
cmake --build --preset windows-debug       # 构建 Windows Debug
cmake --build --preset macos-release       # 构建 macOS Release
# ... 其他预设同理

# === 测试 ===
ctest --preset windows-debug               # 运行 Windows Debug 测试
ctest --preset macos-debug                 # 运行 macOS Debug 测试
# Android 测试需要推送到设备或模拟器

# === 冒烟测试 ===
cmake --build --preset <当前平台>-debug --target all && ctest --preset <当前平台>-debug --output-on-failure
```

**最低验证标准**：每次改动后，当前平台的 `cmake --build + ctest` 必须以 exit 0 结束。

---

## 按任务类型决定先读什么

| 任务类型 | 先读这些文件 |
|---------|------------|
| 核心逻辑 Bug / 功能 | `src/core/` 相关模块、`include/` 对应头文件 |
| 平台特定问题 | `src/platform/<平台>/`、`platforms/<平台>.md` |
| 构建 / CMake 问题 | `CMakeLists.txt`（顶层）、`CMakePresets.json`、出问题模块的 `CMakeLists.txt` |
| 依赖问题 | `vcpkg.json`、`cmake/modules/` |
| 测试问题 | `tests/CMakeLists.txt`、对应的 `*_test.cpp` |
| API 设计 | `include/<项目名>/`、`src/platform/platform.h` |
| Android / JNI | `src/platform/android/`、`cmake/toolchains/android.toolchain.cmake` |

---

## 已知的坑 / 特殊说明

- **MSVC 与 GCC/Clang 的模板实例化差异**：MSVC 对 two-phase lookup 不够严格，某些模板代码在 MSVC 上编译通过但在 Clang 上报错。始终在至少两个平台上验证模板代码。
- **Android NDK 的 STL**：使用 c++_shared（而非 c++_static），避免多个共享库各自链接一份 STL 导致 ODR 违规。
- **macOS universal binary**：如果需要同时支持 x86_64 和 arm64，使用 `CMAKE_OSX_ARCHITECTURES="x86_64;arm64"`。
- **Windows DLL 导出**：MSVC 默认不导出任何符号。必须使用 `__declspec(dllexport)` 或 CMake 的 `GenerateExportHeader`。
- **vcpkg triplet**：Windows 用 `x64-windows`，macOS 用 `x64-osx` 或 `arm64-osx`，Android 用 `arm64-android`。确保 `VCPKG_TARGET_TRIPLET` 与预设一致。
- **std::filesystem**：Android NDK 旧版本对 `<filesystem>` 支持不完整，确认 NDK r25+ 且 API level >= 24。
- **#pragma once vs include guard**：本项目统一用 `#pragma once`，所有主流编译器均支持。
