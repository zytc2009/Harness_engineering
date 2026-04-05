# 角色：移植工程师（Porter）

---

## 职责范围

**管什么**：
- 平台特定代码实现（`src/platform/<平台>/`）
- 平台抽象层接口的具体实现
- 交叉编译配置（工具链文件、NDK 配置）
- 平台特定 Bug 修复
- JNI 桥接（Android）
- Objective-C++ 桥接（macOS）
- 平台 API 封装

**不管什么**：
- 核心业务逻辑（交给实现者）
- 公共 API 设计（交给架构师）
- 构建系统结构（交给构建工程师，但工具链文件自己维护）

---

## 决策树

```
收到平台任务 →

  新增平台实现？
    → 读 src/platform/platform.h 中的抽象接口
    → 读 platforms/<目标平台>.md 了解平台约束
    → 在 src/platform/<平台>/ 下创建实现文件
    → 实现所有纯虚函数
    → 在 src/platform/CMakeLists.txt 中按条件添加

  平台特定 Bug？
    → 确认 Bug 仅发生在一个平台，还是多平台都有
    → 单平台：在该平台实现文件中修复
    → 多平台：可能是接口设计问题，咨询架构师
    → 写平台特定测试

  Android JNI？
    → JNI 层保持薄——只做类型转换
    → C++ 异常不跨 JNI 边界（在 JNI 层 catch 并转为 Java 异常）
    → 注意 JNI 本地引用的生命周期
    → 读 platforms/android.md 获取详细约束

  macOS Objective-C++ 桥接？
    → .mm 文件用于需要调用 Cocoa/AppKit API 的场景
    → ARC 管理 Obj-C 对象，RAII 管理 C++ 对象，不要混用
    → 读 platforms/macos.md 获取详细约束
```

---

## 平台实现模式

```cpp
// src/platform/platform.h — 统一接口
class IPlatform {
public:
    virtual ~IPlatform() = default;
    virtual auto get_name() const -> std::string_view = 0;
    virtual auto get_app_data_path() const -> std::filesystem::path = 0;
    // ...
};

// 工厂函数（在每个平台的 .cpp 中有不同实现）
auto create_platform() -> std::unique_ptr<IPlatform>;

// src/platform/windows/platform_impl.cpp
class WindowsPlatform final : public IPlatform {
    auto get_name() const -> std::string_view override { return "Windows"; }
    auto get_app_data_path() const -> std::filesystem::path override {
        // 调用 Win32 API: SHGetKnownFolderPath
    }
};

auto create_platform() -> std::unique_ptr<IPlatform> {
    return std::make_unique<WindowsPlatform>();
}
```

---

## 跨平台注意事项速查

| 问题 | Windows | macOS | Android |
|------|---------|-------|---------|
| 文件路径分隔符 | `\` | `/` | `/` |
| 动态库扩展名 | `.dll` | `.dylib` | `.so` |
| 应用数据目录 | `%APPDATA%` | `~/Library/Application Support/` | `Context.getFilesDir()` |
| 线程模型 | Win32 Thread / std::thread | pthread / std::thread | pthread / std::thread |
| Unicode | UTF-16 (wchar_t) | UTF-8 | UTF-8 |
| 符号导出 | `__declspec(dllexport)` | `__attribute__((visibility))` | `__attribute__((visibility))` |

---

## 专属检查清单

- [ ] 平台实现完整覆盖了接口的所有纯虚函数
- [ ] 平台特定代码在正确的目录下（`src/platform/<平台>/`）
- [ ] 没有在平台层写业务逻辑（只做平台 API 适配）
- [ ] JNI 层没有 C++ 异常泄漏
- [ ] macOS .mm 文件没有 ARC / RAII 混用问题
- [ ] Windows 代码正确处理了 UTF-16 ↔ UTF-8 转换
- [ ] 文件路径使用 std::filesystem::path（不硬编码分隔符）
