# 输入输出地图（IO MAP）— 跨平台 C++20 项目
> 从哪里读取输入。往哪里写输出。

---

## 输入 — 从哪里读

### 配置文件

| 配置项 | 位置 | 格式 | 控制什么 |
|--------|------|------|---------|
| 项目顶层配置 | `CMakeLists.txt` | CMake | 项目名、版本、全局编译选项 |
| 构建预设 | `CMakePresets.json` | JSON | 平台 × 构建类型的所有组合 |
| 依赖清单 | `vcpkg.json` | JSON | 第三方库名称 + 版本约束 |
| 工具链定义 | `cmake/toolchains/*.cmake` | CMake | 交叉编译器路径、sysroot、目标架构 |
| 代码格式化 | `.clang-format` | YAML | clang-format 规则 |
| 静态分析 | `.clang-tidy` | YAML | clang-tidy 检查项 |
| vcpkg 注册表 | `vcpkg-configuration.json` | JSON | 自定义注册表、版本基线 |

### 运行时上下文

| 信息 | 如何获取 |
|------|---------|
| 当前平台 | CMake: `CMAKE_SYSTEM_NAME`（Windows / Darwin / Android） |
| 编译器 | CMake: `CMAKE_CXX_COMPILER_ID`（MSVC / AppleClang / Clang） |
| 构建类型 | CMake: `CMAKE_BUILD_TYPE` 或多配置生成器的 `--config` |
| 目标架构 | CMake: `CMAKE_SYSTEM_PROCESSOR`（x86_64 / arm64 / aarch64） |
| Android API 级别 | CMake: `ANDROID_PLATFORM`（android-24） |
| vcpkg 工具链 | 环境变量 `VCPKG_ROOT` 或 CMakePresets 中的 `CMAKE_TOOLCHAIN_FILE` |

### 环境变量

```
VCPKG_ROOT          — vcpkg 安装路径
ANDROID_NDK_HOME    — Android NDK 路径
ANDROID_SDK_ROOT    — Android SDK 路径
CMAKE_GENERATOR     — 首选生成器（Ninja / Visual Studio 17 2022）
CC                  — C 编译器覆盖（可选）
CXX                 — C++ 编译器覆盖（可选）
```

---

## 输出 — 往哪里写

### 代码改动

| 新增内容 | 写在这里 | 文件命名规范 |
|---------|---------|------------|
| 公共头文件 | `include/<项目名>/` | `snake_case.h` |
| 核心模块头文件 | `src/core/` | `snake_case.h` |
| 核心模块实现 | `src/core/` | `snake_case.cpp` |
| 平台实现（Windows） | `src/platform/windows/` | `snake_case.cpp` |
| 平台实现（macOS） | `src/platform/macos/` | `snake_case.cpp` 或 `snake_case.mm`（Obj-C++） |
| 平台实现（Android） | `src/platform/android/` | `snake_case.cpp` |
| JNI 桥接 | `src/platform/android/jni/` | `snake_case_jni.cpp` |
| 单元测试 | `tests/core/` | `<模块名>_test.cpp` |
| 平台测试 | `tests/platform/` | `<模块名>_<平台>_test.cpp` |
| CMake 模块 | `cmake/modules/` | `Find<PackageName>.cmake` 或 `<功能>.cmake` |
| 工具链文件 | `cmake/toolchains/` | `<平台>.toolchain.cmake` |

### CMake 注册（实现完成后最后处理）

| 新增内容 | 注册文件 | 如何添加 |
|---------|---------|---------|
| 新核心源文件 | `src/core/CMakeLists.txt` | 加入 `target_sources()` |
| 新平台源文件 | `src/platform/CMakeLists.txt` | 按 `if(WIN32)` / `if(APPLE)` / `if(ANDROID)` 条件添加 |
| 新测试文件 | `tests/CMakeLists.txt` | `add_test()` 或 `gtest_discover_tests()` |
| 新可执行目标 | `app/CMakeLists.txt` | `add_executable()` + `target_link_libraries()` |
| 新库目标 | 对应子目录 `CMakeLists.txt` | `add_library()` + `target_link_libraries()` |
| 新第三方依赖 | `vcpkg.json` + 对应 `CMakeLists.txt` | `find_package()` + `target_link_libraries()` |
| 新公共头文件 | `include/` 对应 `CMakeLists.txt` | `target_sources(... PUBLIC FILE_SET HEADERS)` 或 install 规则 |

### 构建产物路径

```
build/
  <preset-name>/          每个预设一个构建目录
    bin/                  可执行文件
    lib/                  静态库 / 动态库
    tests/                测试可执行文件
    _deps/                vcpkg / FetchContent 拉取的依赖

# Android 特殊产物
build/android-release/
  lib/<ABI>/              .so 文件（arm64-v8a / armeabi-v7a）
```

### 平台条件编译宏映射

```cpp
// CMake 自动定义，不要手动 #define
_WIN32              → Windows（MSVC）
__APPLE__           → macOS（Apple Clang）
__ANDROID__         → Android（NDK Clang）

// 项目自定义平台宏（在 CMakeLists.txt 中通过 target_compile_definitions 设置）
<PROJECT>_PLATFORM_WINDOWS
<PROJECT>_PLATFORM_MACOS
<PROJECT>_PLATFORM_ANDROID

// 正确用法：仅在 src/platform/ 内部使用
#if defined(<PROJECT>_PLATFORM_WINDOWS)
  #include "platform/windows/impl.h"
#elif defined(<PROJECT>_PLATFORM_MACOS)
  #include "platform/macos/impl.h"
#elif defined(<PROJECT>_PLATFORM_ANDROID)
  #include "platform/android/impl.h"
#endif

// 禁止用法：在 src/core/ 或 app/ 中直接使用平台宏
```

---

## 状态管理约定

```cpp
// 正确模式：不可变值对象 + 工厂方法
auto config = Config::create(params);
auto updated = config.with_timeout(new_timeout);  // 返回新对象

// 禁止的反模式：
config.timeout = new_timeout;  // ← 永远不要这样做
config.set_timeout(new_timeout);  // ← 如果这个方法修改 this，也不要用
```

---

## 禁止写入文件的内容

- 密钥 / 凭证 / Token — 使用环境变量或平台密钥链
- 绝对路径 — 使用 CMake 变量或相对路径
- 平台特定的 `#ifdef` 在 `src/core/` 或 `app/` 中 — 只允许在 `src/platform/` 中
- 第三方库的头文件在 `include/` 公共 API 中泄漏 — 用前向声明或 Pimpl 隔离
