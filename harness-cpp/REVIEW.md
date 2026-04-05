# 审查检查清单（REVIEW）— 跨平台 C++20 项目
> 标记任务完成前必须过一遍。
> 第 0–4 节通用。第 5–9 节为 C++ / 跨平台专属。

---

## 0. 启动检查（强制，第一步执行）

```bash
cmake --build --preset <当前平台>-debug && ctest --preset <当前平台>-debug --output-on-failure
```

**如果失败 → 停止。修复。重新运行。在启动通过之前不得继续任何其他检查。**

---

## 0.5 Git 变更范围检查（强制，第二步执行）

先用 Git 确定本次改动的精确范围，后续所有检查只针对这些文件。

```bash
# 查看工作区状态
git status

# 查看完整改动内容
git diff                    # 未暂存
git diff --cached           # 已暂存

# 查看改动统计（快速了解影响面）
git diff --stat
git diff --cached --stat

# 如果在分支上，查看整个分支的改动
git diff main..HEAD --stat
```

- [ ] 已确定改动文件清单（后续检查只审查这些文件）
- [ ] 没有不该提交的文件：
  - 构建产物（`*.o`、`*.obj`、`*.exe`、`*.dll`、`*.so`、`*.dylib`、`build/`）
  - 密钥文件（`.env`、`*.key`、`*.pem`、`*.p12`）
  - IDE 配置（`.vs/`、`.idea/`、`*.user`、`.DS_Store`）
  - 临时文件（`*.tmp`、`*.log`、`*.bak`）
- [ ] 改动全部在任务范围内（没有混入无关修改）
- [ ] 新增文件的路径符合 `IO_MAP.md` 的目录约定
- [ ] `.gitignore` 覆盖了需要忽略的文件类型

---

## 1. 正确性

- [ ] 改动后的代码是否满足任务要求？（重新读一遍原始需求）
- [ ] 你是否手动执行了受影响的路径——不只是读代码？
- [ ] 你是否至少测试了一个成功案例和一个失败 / 边界案例？
- [ ] 如果任务有明确的验收标准，是否全部满足？

---

## 2. 不可变性 / RAII

- [ ] 没有裸 `new` / `delete`（使用 `std::unique_ptr` / `std::make_unique`）
- [ ] 值对象不可原地修改（提供 `with_xxx()` 方法返回新对象）
- [ ] 没有对容器元素的悬垂引用（迭代时不修改容器）
- [ ] 资源获取即初始化——文件句柄、锁、网络连接都在构造时获取、析构时释放
- [ ] `std::shared_ptr` 仅用于真正的共享所有权场景，不滥用

---

## 3. 安全性

- [ ] 任何文件中都没有硬编码的密钥、API Key、Token 或密码
- [ ] 所有外部输入（文件、网络、JNI 参数）在使用前经过校验
- [ ] 没有 buffer overflow 风险（使用 `std::string`、`std::vector`、`std::span` 而非裸数组）
- [ ] 没有 format string 漏洞（使用 `std::format` 或 `fmt::format`，不用 `sprintf`）
- [ ] 错误信息不会向用户泄露内部路径或内存地址

---

## 4. 错误处理

- [ ] 使用 `Result<T, E>` / `std::expected` 返回错误，不用异常做控制流
- [ ] 所有可能失败的操作都检查了返回值
- [ ] 错误信息包含足够的上下文（什么操作、在哪里失败、为什么）
- [ ] 异常不跨模块边界传播（特别是不跨 DLL / .so / JNI 边界）

---

## 5. 内存安全（C++ 专属）

- [ ] 没有 use-after-free（检查指针 / 引用的生命周期）
- [ ] 没有 double-free（所有权唯一，`unique_ptr` 转移清晰）
- [ ] 没有未初始化变量（C++20: 使用 designated initializers 或默认成员初始化）
- [ ] 移动语义正确（移动后的对象处于有效但未指定状态，不再使用）
- [ ] `std::string_view` / `std::span` 不持有悬垂指针（底层数据的生命周期 >= view 的生命周期）
- [ ] 多线程场景：共享数据有 mutex 保护，或使用 atomic

---

## 6. ABI 兼容性（库目标专属）

- [ ] 公共头文件（`include/`）的改动是否向后兼容？
  - 新增函数 / 类型：安全
  - 修改函数签名、虚函数顺序、成员布局：**破坏性变更**，需要版本号提升
- [ ] 导出宏（`MY_API`）是否正确使用？新的公共函数是否标记了导出？
- [ ] Pimpl 模式是否用于隐藏实现细节、稳定 ABI？
- [ ] 没有在公共头文件中暴露第三方库的类型

---

## 7. 跨平台兼容性

- [ ] 没有使用平台特定 API（POSIX / Win32 / Cocoa）在 `src/core/` 或 `app/` 中
- [ ] 平台特定代码都在 `src/platform/<平台>/` 中
- [ ] 文件路径使用 `std::filesystem::path`（自动处理分隔符）
- [ ] 没有假设字节序（如需要，显式处理）
- [ ] 没有假设 `sizeof(long)` 等平台差异类型的大小（使用 `<cstdint>` 固定宽度类型）
- [ ] 没有使用编译器扩展（`__attribute__`、`__declspec`）在通用代码中——用宏包装
- [ ] 编译器警告干净：`-Wall -Wextra -Wpedantic`（GCC/Clang）、`/W4`（MSVC）

---

## 8. CMake / 构建检查

- [ ] 新源文件已添加到对应的 `CMakeLists.txt`
- [ ] 新依赖已添加到 `vcpkg.json` + `find_package()` + `target_link_libraries()`
- [ ] 使用 `target_*` 命令（不用全局 `include_directories` / `add_definitions`）
- [ ] 库目标正确设置了 `PUBLIC` / `PRIVATE` / `INTERFACE` 传播
- [ ] Android 目标正确配置了 `SHARED` 库类型和 ABI 过滤
- [ ] CMakePresets.json 中受影响的预设仍然能 configure 通过

---

## 9. 代码风格

- [ ] 文件名 `snake_case`，类名 `PascalCase`，函数/变量 `snake_case`
- [ ] 头文件使用 `#pragma once`
- [ ] include 顺序正确（对应头 → 项目内 → 第三方 → 标准库）
- [ ] 改动文件在大小限制内（头文件 < 300 行，实现 < 500 行，最大 800 行）
- [ ] 函数 < 50 行，嵌套 < 4 层
- [ ] 宏带项目前缀，避免命名冲突
- [ ] 没有遗留 `TODO` 在生产路径中

---

## 10. 收尾输出

所有检查通过后：

1. 输出简短总结：改了什么、为什么改、影响哪些平台。
2. 使用祈使句主题行提交：`feat: xxx`、`fix: xxx`、`refactor: xxx`。
3. 在提交正文中记录：影响的平台、ABI 兼容性、已知的权衡。
