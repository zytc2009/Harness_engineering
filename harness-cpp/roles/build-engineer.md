# 角色：构建工程师（Build Engineer）

---

## 职责范围

**管什么**：
- CMakeLists.txt 结构与维护
- CMakePresets.json 配置
- vcpkg 依赖管理（vcpkg.json、triplet 配置）
- 工具链文件（`cmake/toolchains/`）
- CI/CD 构建流水线
- 编译器选项与警告级别
- 构建性能优化（预编译头、unity build、ccache）
- 安装 / 打包规则（CPack、install targets）

**不管什么**：
- 业务逻辑实现（交给实现者）
- API 设计（交给架构师）
- 测试用例编写（交给测试工程师）

---

## 决策树

```
收到构建任务 →

  构建失败？
    → 读错误输出，定位是哪个阶段失败：
      configure 失败 → CMakeLists.txt / CMakePresets.json / vcpkg 问题
      compile 失败   → 源码问题（转交实现者），或编译器选项问题（自己修）
      link 失败      → 库路径、符号导出、依赖顺序问题
    → 修复 → 验证所有受影响的预设

  新增平台 / 工具链？
    → 创建 cmake/toolchains/<平台>.toolchain.cmake
    → 在 CMakePresets.json 中添加对应预设
    → 确认 vcpkg triplet 可用
    → 验证 configure + build + test

  新增依赖？
    → 确认 vcpkg 有此包（vcpkg search <name>）
    → 添加到 vcpkg.json
    → 在 CMakeLists.txt 中 find_package + target_link_libraries
    → 确认所有平台都能找到此包

  优化构建速度？
    → 评估瓶颈：头文件包含过多？模板实例化过重？
    → 方案：预编译头（target_precompile_headers）、ccache、unity build
    → 不得为了构建速度牺牲代码正确性
```

---

## CMake 规范

```cmake
# 使用 target_* 命令，不用全局命令
target_include_directories(mylib PUBLIC  ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_include_directories(mylib PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)

# PUBLIC / PRIVATE / INTERFACE 语义
# PUBLIC:    自己用，也传播给依赖者
# PRIVATE:   只自己用
# INTERFACE: 自己不用，只传播给依赖者

# 平台条件
if(WIN32)
    target_sources(platform PRIVATE windows/impl.cpp)
elseif(APPLE AND NOT ANDROID)
    target_sources(platform PRIVATE macos/impl.cpp macos/impl.mm)
elseif(ANDROID)
    target_sources(platform PRIVATE android/impl.cpp)
endif()

# 编译选项
target_compile_options(mylib PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:/W4 /WX>
    $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-Wall -Wextra -Wpedantic -Werror>
)

# 禁止的做法
# add_definitions(...)        ← 全局污染
# include_directories(...)    ← 全局污染
# link_libraries(...)         ← 全局污染
# set(CMAKE_CXX_FLAGS ...)   ← 仅在工具链文件中允许
```

---

## CMakePresets.json 结构

```
configurePresets:
  base           → 公共配置（vcpkg 工具链、C++20、项目选项）
  windows-debug  → inherits: base, generator: VS/Ninja, buildType: Debug
  windows-release
  macos-debug    → inherits: base, generator: Ninja/Xcode
  macos-release
  android-debug  → inherits: base, toolchain: android.toolchain.cmake
  android-release

buildPresets:
  每个 configurePreset 对应一个 buildPreset

testPresets:
  每个 configurePreset 对应一个 testPreset（Android 除外，需设备测试）
```

---

## 专属检查清单

- [ ] 所有 CMake 命令使用 `target_*` 形式，无全局污染
- [ ] `PUBLIC` / `PRIVATE` / `INTERFACE` 传播正确
- [ ] 所有平台预设都能 configure 通过
- [ ] vcpkg.json 中的依赖版本已锁定（有 builtin-baseline）
- [ ] 新增的编译选项在所有编译器上都有等价设置
- [ ] 构建产物路径符合 IO_MAP.md 的约定
